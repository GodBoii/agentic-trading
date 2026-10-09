"""Small neural controls with train-only scaling and validation checkpointing."""

from copy import deepcopy
from dataclasses import dataclass
import random

import numpy as np
import torch
from torch import nn

SEEDS = (17, 29, 43)
MAX_EPOCHS = 12
BATCH_SIZE = 512
PATIENCE = 3
MINIMUM_IMPROVEMENT = 1e-6


def deterministic(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)


def validate_inputs(sequence: np.ndarray, context: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    sequence, context = np.asarray(sequence), np.asarray(context)
    if (sequence.ndim != 3 or sequence.shape[1] != 30 or sequence.shape[2] < 1
            or context.ndim != 2 or len(sequence) != len(context)
            or not np.isfinite(sequence).all() or not np.isfinite(context).all()):
        raise ValueError("aligned finite 30-bar sequences and context matrix required")
    return sequence, context


def tabular(sequence: np.ndarray, context: np.ndarray) -> np.ndarray:
    sequence, context = validate_inputs(sequence, context)
    return np.column_stack((context, sequence.mean(axis=1), sequence.std(axis=1),
                            sequence[:, -1], sequence.sum(axis=1))).astype(np.float32)


@dataclass(frozen=True)
class Scaler:
    sequence_mean: tuple[float, ...]
    sequence_scale: tuple[float, ...]
    context_mean: tuple[float, ...]
    context_scale: tuple[float, ...]
    target_mean: float
    target_scale: float

    @classmethod
    def fit(cls, sequence: np.ndarray, context: np.ndarray, target: np.ndarray) -> "Scaler":
        sequence, context = validate_inputs(sequence, context)
        target = np.asarray(target, dtype=float)
        if target.shape != (len(sequence),) or len(target) < 2 or not np.isfinite(target).all():
            raise ValueError("aligned finite training targets required")
        mean, scale = sequence.astype(float).mean(axis=(0, 1)), sequence.astype(float).std(axis=(0, 1))
        offset, context_scale = context.astype(float).mean(axis=0), context.astype(float).std(axis=0)
        scale[scale < 1e-8], context_scale[context_scale < 1e-8] = 1, 1
        return cls(tuple(mean), tuple(scale), tuple(offset), tuple(context_scale),
                   float(target.mean()), max(float(target.std()), 1e-8))

    def transform(self, sequence: np.ndarray, context: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        sequence, context = validate_inputs(sequence, context)
        if sequence.shape[2] != len(self.sequence_mean) or context.shape[1] != len(self.context_mean):
            raise ValueError("prediction channel dimensions differ from training scaler")
        return (np.clip((sequence - self.sequence_mean) / self.sequence_scale, -10, 10).astype(np.float32),
                np.clip((context - self.context_mean) / self.context_scale, -10, 10).astype(np.float32))


class ForecastNetwork(nn.Module):
    def __init__(self, architecture: str, channels: int, context_columns: int):
        super().__init__()
        if architecture not in {"mlp", "gru"} or channels < 1 or context_columns < 0:
            raise ValueError("known architecture and valid input dimensions required")
        self.architecture = architecture
        if architecture == "gru":
            self.recurrent = nn.GRU(channels, 16, batch_first=True)
            self.head = nn.Sequential(nn.Linear(16 + context_columns, 16), nn.ReLU(), nn.Linear(16, 1))
        else:
            self.head = nn.Sequential(nn.Linear(context_columns + channels * 4, 32), nn.ReLU(),
                                      nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 1))

    def forward(self, sequence: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        if self.architecture == "gru":
            _, hidden = self.recurrent(sequence)
            features = torch.cat((hidden[-1], context), dim=1)
        else:
            features = torch.cat((context, sequence.mean(dim=1), sequence.std(dim=1, correction=0),
                                  sequence[:, -1], sequence.sum(dim=1)), dim=1)
        return self.head(features).squeeze(-1)


def predict_normalized(model: ForecastNetwork, sequence: np.ndarray, context: np.ndarray) -> np.ndarray:
    sequence, context = validate_inputs(sequence, context)
    model.eval()
    results = []
    with torch.inference_mode():
        for start in range(0, len(sequence), BATCH_SIZE):
            result = model(torch.as_tensor(sequence[start:start + BATCH_SIZE], dtype=torch.float32),
                           torch.as_tensor(context[start:start + BATCH_SIZE], dtype=torch.float32))
            results.append(result.numpy())
    return np.concatenate(results) if results else np.empty(0, dtype=np.float32)


def fit_network(architecture: str, seed: int, train_sequence: np.ndarray, train_context: np.ndarray,
                train_target: np.ndarray, validation_sequence: np.ndarray, validation_context: np.ndarray,
                validation_target: np.ndarray, max_epochs: int = MAX_EPOCHS) -> tuple[ForecastNetwork, dict]:
    """Inputs and targets already use the frozen training-only scaler."""
    train_sequence, train_context = validate_inputs(train_sequence, train_context)
    validation_sequence, validation_context = validate_inputs(validation_sequence, validation_context)
    train_target, validation_target = np.asarray(train_target), np.asarray(validation_target)
    if (train_target.shape != (len(train_sequence),) or validation_target.shape != (len(validation_sequence),)
            or not len(train_target) or not len(validation_target) or not np.isfinite(train_target).all()
            or not np.isfinite(validation_target).all() or max_epochs < 1):
        raise ValueError("nonempty aligned finite train and validation targets required")
    deterministic(seed)
    model = ForecastNetwork(architecture, train_sequence.shape[2], train_context.shape[1])
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.001)
    generator = torch.Generator().manual_seed(seed)
    sequence_tensor = torch.as_tensor(train_sequence, dtype=torch.float32)
    context_tensor = torch.as_tensor(train_context, dtype=torch.float32)
    target_tensor = torch.as_tensor(train_target, dtype=torch.float32)
    history, best_loss, best_state, best_epoch, waiting = [], float("inf"), None, 0, 0
    for epoch in range(1, max_epochs + 1):
        model.train()
        ordering = torch.randperm(len(train_target), generator=generator)
        training_sum = 0.0
        for start in range(0, len(ordering), BATCH_SIZE):
            indices = ordering[start:start + BATCH_SIZE]
            optimizer.zero_grad(set_to_none=True)
            prediction = model(sequence_tensor[indices], context_tensor[indices])
            loss = nn.functional.mse_loss(prediction, target_tensor[indices])
            if not torch.isfinite(loss):
                raise ValueError("neural loss became nonfinite")
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5, error_if_nonfinite=True)
            optimizer.step()
            training_sum += float(loss.detach()) * len(indices)
        validation_prediction = predict_normalized(model, validation_sequence, validation_context)
        validation_loss = float(np.mean((validation_prediction.astype(float) - validation_target) ** 2))
        history.append({"epoch": epoch, "training_mse": training_sum / len(train_target),
                        "validation_mse": validation_loss})
        if validation_loss < best_loss - MINIMUM_IMPROVEMENT:
            best_loss, best_epoch, waiting = validation_loss, epoch, 0
            best_state = deepcopy(model.state_dict())
        else:
            waiting += 1
        if waiting >= PATIENCE:
            break
    if best_state is None:
        raise ValueError("no finite validation checkpoint")
    model.load_state_dict(best_state)
    model.eval()
    return model, {"architecture": architecture, "seed": seed, "selected_epoch": best_epoch,
                   "selected_validation_mse": best_loss, "history": history,
                   "parameters": sum(parameter.numel() for parameter in model.parameters())}


def fit_ridge(features: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    features, target = np.asarray(features, dtype=float), np.asarray(target, dtype=float)
    if (features.ndim != 2 or target.shape != (len(features),) or not len(features)
            or not np.isfinite(features).all() or not np.isfinite(target).all()):
        raise ValueError("aligned finite tabular ridge input required")
    mean, scale = features.mean(axis=0), features.std(axis=0)
    scale[scale < 1e-8] = 1
    design = np.column_stack((np.ones(len(features)), (features - mean) / scale))
    penalty = np.eye(design.shape[1]) * len(features) * .01
    penalty[0, 0] = 0
    coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ target)
    return mean, scale, coefficients


def ridge_predict(features: np.ndarray, fitted: tuple[np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
    mean, scale, coefficients = fitted
    return np.column_stack((np.ones(len(features)), (features - mean) / scale)) @ coefficients

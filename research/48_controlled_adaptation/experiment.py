"""Chronological monthly forecasts with an unchanged-model fallback."""

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from .model import METHODS, RidgeModel, fit_method, incumbent_validation_is_unseen, select_challenger

Utility = Callable[[pd.DataFrame, np.ndarray, int], float]


@dataclass(frozen=True)
class ForecastRun:
    predictions: dict[str, np.ndarray]
    deployment_log: list[dict]
    models: dict[str, dict]


def chronological_forecasts(
    frame: pd.DataFrame, features: list[str], horizon: int, utility: Utility, *, controlled: bool = True
) -> ForecastRun:
    """Only prior mature labels may train any deployed or shadow model."""
    if not frame.index.equals(pd.RangeIndex(len(frame))):
        raise ValueError("frame must have unique contiguous positional index")
    required = {*features, "target", "label_end", "date"}
    if not required.issubset(frame):
        raise ValueError(f"missing shared dataset columns: {sorted(required - set(frame))}")
    evaluated = frame.date >= "2024-01-01"
    periods = sorted(pd.to_datetime(frame.loc[evaluated, "date"]).dt.strftime("%Y-%m").unique())
    names = (*METHODS, "controlled_selector") if controlled else METHODS
    predictions = {method: np.full(len(frame), np.nan) for method in names}
    log: list[dict] = []
    models: dict[str, dict] = {}

    def retain(model: RidgeModel) -> str:
        models.setdefault(model.digest, model.payload())
        return model.digest

    static = fit_method(frame, features, "2024-01-01", "static_ridge")
    incumbent = static
    retain(static)
    for month in periods:
        boundary = month + "-01"
        month_mask = pd.to_datetime(frame.date).dt.strftime("%Y-%m") == month
        positions = np.flatnonzero(month_mask.to_numpy())
        x = frame.loc[month_mask, features].to_numpy()
        for method in METHODS:
            model = static if method == "static_ridge" else fit_method(frame, features, boundary, method)
            before = retain(model)
            predictions[method][positions] = model.predict(x)
            if model.digest != before:
                raise ValueError("deployed model mutated during prediction")
            log.append({"horizon": horizon, "month": month, "policy": method, "decision": "static_keep" if method == "static_ridge" else "scheduled_refit",
                        "deployment_model_sha256": before, "training_rows": model.training_rows,
                        "last_training_label_end": model.last_label_end})

        if not controlled:
            continue
        previous_dates = sorted(frame.loc[(frame.date >= "2024-01-01") & (frame.date < boundary), "date"].unique())
        record = {"horizon": horizon, "month": month, "policy": "controlled_selector",
                  "incumbent_before_sha256": retain(incumbent), "incumbent_method": incumbent.method}
        if len(previous_dates) < 60:
            record["decision"] = "waiting_initial_60date_validation"
        else:
            validation_dates = previous_dates[-60:]
            first_date = validation_dates[0]
            record["validation_dates"] = validation_dates
            if not incumbent_validation_is_unseen(incumbent, first_date):
                record["decision"] = "waiting_unseen60date_validation"
            else:
                # Last validation targets must also be mature before deployment.
                utc_boundary = pd.Timestamp(boundary).tz_localize("Asia/Kolkata").tz_convert("UTC")
                validation_mask = frame.date.isin(validation_dates) & (pd.to_datetime(frame.label_end, utc=True) < utc_boundary)
                validation = frame.loc[validation_mask].copy().reset_index(drop=True)
                vx, vy = validation[features].to_numpy(), validation.target.to_numpy()
                current_prediction = incumbent.predict(vx)
                scores = {"actual_incumbent": {"mae": float(np.mean(np.abs(current_prediction - vy))),
                                               "net_utility": utility(validation, current_prediction, horizon)}}
                record["shadow_fit_cutoff"] = first_date
                record["last_validation_label_end"] = str(validation.label_end.max())
                record["shadow_model_hashes"] = {}
                for method in METHODS:
                    shadow = static if method == "static_ridge" else fit_method(frame, features, first_date, method)
                    if not incumbent_validation_is_unseen(shadow, first_date):
                        raise ValueError("challenger training contaminated validation block")
                    shadow_prediction = shadow.predict(vx)
                    scores[method] = {"mae": float(np.mean(np.abs(shadow_prediction - vy))),
                                      "net_utility": utility(validation, shadow_prediction, horizon)}
                    record["shadow_model_hashes"][method] = retain(shadow)
                chosen, reason = select_challenger(scores, "actual_incumbent")
                record["scores"] = scores
                record["decision"] = reason
                record["chosen_shadow_method"] = chosen
                if chosen != "actual_incumbent":
                    incumbent = static if chosen == "static_ridge" else fit_method(frame, features, boundary, chosen)
        prediction_hash = retain(incumbent)
        predictions["controlled_selector"][positions] = incumbent.predict(x)
        if incumbent.digest != prediction_hash:
            raise ValueError("controlled model changed within deployed month")
        record.update({"deployment_model_sha256": prediction_hash, "deployed_method": incumbent.method,
                       "last_training_label_end": incumbent.last_label_end, "training_rows": incumbent.training_rows})
        log.append(record)
    for method, predicted in predictions.items():
        if not np.isfinite(predicted[evaluated]).all():
            raise ValueError(f"missing deployed forecasts for {method}")
    return ForecastRun(predictions, log, models)

from importlib import import_module

import numpy as np
import pandas as pd
import pytest

module = import_module("research.48_controlled_adaptation.model")


def test_label_maturity_not_observation_date_controls_training() -> None:
    frame = pd.DataFrame({"date": ["2023-12-29", "2023-12-29", "2024-01-02"],
                          "label_end": ["2023-12-29T09:00:00Z", "2024-01-01T00:00:00Z", "2024-01-02T09:00:00Z"]})
    assert module.training_mask(frame, "2024-01-01", "expanding_monthly").tolist() == [True, False, False]


def test_rolling_window_respects_calendar_year() -> None:
    frame = pd.DataFrame({"date": ["2023-12-29", "2024-01-02", "2024-12-30"],
                          "label_end": ["2023-12-29T09:00:00Z", "2024-01-02T09:00:00Z", "2024-12-30T09:00:00Z"]})
    assert module.training_mask(frame, "2025-01-01", "rolling_12month_monthly").tolist() == [False, True, True]
    assert module.training_mask(frame, "2025-01-01", "static_ridge").tolist() == [True, False, False]


def test_half_life_counts_observed_dates_not_rows() -> None:
    dates = pd.Series([str(index).zfill(3) for index in range(91)] + ["090"])
    weights = module.recency_weights(dates)
    assert weights[0] == 0.5
    assert weights[-1] == weights[-2] == 1.0


def test_scaler_and_model_arrays_are_immutable() -> None:
    x = np.array([[0, 5], [1, 5], [2, 5]], float)
    model = module.fit_ridge(x, np.array([1, 3, 5]), np.ones(3), method="static_ridge",
                             last_label_end="2023-12-29T00:00:00Z")
    before = model.digest
    model.predict(np.array([[1000, 5]], float))
    assert model.digest == before
    assert model.mean.tolist() == [1, 5]
    assert model.scale[1] == 1
    with pytest.raises(ValueError):
        model.coefficients[0] = 100
    assert module.incumbent_validation_is_unseen(model, "2024-01-01")
    assert not module.incumbent_validation_is_unseen(model, "2023-12-01")


def test_gate_rejects_better_error_if_cost_utility_worse() -> None:
    scores = {"static_ridge": {"mae": 10.0, "net_utility": 0.0},
              "rolling_12month_monthly": {"mae": 9.0, "net_utility": -1.0},
              "expanding_monthly": {"mae": 9.95, "net_utility": 1.0}}
    assert module.select_challenger(scores, "static_ridge")[0] == "static_ridge"
    scores["rolling_12month_monthly"]["net_utility"] = 0.1
    assert module.select_challenger(scores, "static_ridge")[0] == "rolling_12month_monthly"

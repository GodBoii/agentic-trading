import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("dependence_study", Path(__file__).with_name("study.py"))
study = importlib.util.module_from_spec(spec); spec.loader.exec_module(study)


def test_exact_day_family_preserves_joint_signs():
    result = study.exact_family_test(np.ones((4, 2)))
    assert result["raw_p"] == [1/16, 1/16]
    assert result["max_stat_adjusted_p"] == [1/16, 1/16]


def test_family_adjustment_cannot_reduce_raw_p():
    result = study.exact_family_test(np.array([[1,4],[-2,1],[3,-1],[1,-3]], dtype=float))
    assert np.all(np.array(result["max_stat_adjusted_p"]) >= result["raw_p"])


def test_bootstrap_handles_constant_and_rejects_nan():
    assert study.bootstrap_interval(np.ones(4), 100) == [1,1]
    with pytest.raises(ValueError): study.bootstrap_interval(np.array([np.nan]))


def test_synthetic_selection_is_not_fresh_edge():
    results = study.null_search_simulation()
    assert results[-1]["mean_selected_training_return"] > results[0]["mean_selected_training_return"] + .5
    assert abs(results[-1]["mean_selected_fresh_return"]) < .02

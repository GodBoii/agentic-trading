import numpy as np
import pandas as pd
import pytest

from freeze_hypothesis import linear_predict, save_frozen_bundle
from run_program import run_one


def test_frozen_coefficients_predict_explicit_formula():
    bundle={'features':['x'],'mean':[2.],'scale':[2.],'coefficients':[3.],'intercept':1.}
    assert linear_predict(bundle,pd.DataFrame({'x':[2.,4.]})).tolist()==[1.,4.]
    with pytest.raises(ValueError): linear_predict(bundle,pd.DataFrame({'x':[np.nan]}))


def test_runner_rejects_escape():
    with pytest.raises(ValueError): run_one('../../python-backend','scanner.py')


def test_runner_rejects_nonexistent_script():
    with pytest.raises(ValueError): run_one('05_indicator_patterns','missing.py')


def test_frozen_export_cannot_overwrite_prior_evidence(tmp_path):
    output = tmp_path / "frozen.json"
    save_frozen_bundle(output, {"frozen_on": "2026-10-02", "models": {}})
    before = output.read_bytes()
    with pytest.raises(FileExistsError): save_frozen_bundle(output, {"models": {"new": True}})
    assert output.read_bytes() == before

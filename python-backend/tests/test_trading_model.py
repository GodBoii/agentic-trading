from __future__ import annotations

from pipeline.llm.trading_model import create_multimodal_trading_model


def test_multimodal_model_requests_xhigh_reasoning(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_ENABLE_REASONING", "1")

    model = create_multimodal_trading_model()
    request_params = model.get_request_params()

    assert request_params["reasoning_effort"] == "xhigh"
    assert request_params["extra_body"]["reasoning"] == {
        "enabled": True,
        "exclude": False,
    }
    assert "max_tokens" not in request_params


def test_multimodal_model_omits_reasoning_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_ENABLE_REASONING", "0")

    model = create_multimodal_trading_model()
    request_params = model.get_request_params()

    assert "reasoning_effort" not in request_params
    assert "extra_body" not in request_params

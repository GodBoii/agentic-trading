from __future__ import annotations

from pipeline.llm import trading_model
from pipeline.llm.trading_model import (
    TRADING_AGENT_MODEL_ID,
    create_multimodal_trading_model,
    create_text_trading_model,
)


def test_trading_models_use_deepseek_v4_1_flash(monkeypatch) -> None:
    monkeypatch.setattr(trading_model, "_ENV_LOADED", True)
    monkeypatch.delenv("OPENROUTER_TEXT_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENROUTER_MULTIMODAL_MODEL_ID", raising=False)

    assert create_text_trading_model().id == TRADING_AGENT_MODEL_ID
    assert create_multimodal_trading_model().id == TRADING_AGENT_MODEL_ID


def test_retired_vision_model_environment_is_migrated(monkeypatch) -> None:
    monkeypatch.setenv(
        "OPENROUTER_MULTIMODAL_MODEL_ID",
        "deepseek/deepseek-v4-flash-vision-exp",
    )

    model = create_multimodal_trading_model()

    assert model.id == TRADING_AGENT_MODEL_ID


def test_retired_explicit_model_override_is_migrated() -> None:
    model = create_multimodal_trading_model(
        id="deepseek/deepseek-v4-flash-vision-exp",
    )

    assert model.id == TRADING_AGENT_MODEL_ID


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

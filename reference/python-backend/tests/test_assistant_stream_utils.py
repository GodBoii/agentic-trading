from pathlib import Path

from assistant_stream_utils import build_system_assistant_terminal_message


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent


def _entry(name, status="completed"):
    return {
        "name": name,
        "payload": {"tool_output": {"status": status}},
    }


def test_post_tool_terminal_message_ignores_read_after_text_entry():
    history = [
        _entry("open_app"),
        _entry("input_text"),
        _entry("get_visible_ui_text"),
    ]

    assert build_system_assistant_terminal_message(history) == (
        "I entered the requested text. Please review it before sending."
    )


def test_terminal_message_never_claims_prepared_message_was_sent():
    message = build_system_assistant_terminal_message([_entry("send_message")])

    assert message == "I opened the message composer with your message ready for review."
    assert "sent" not in message.lower()


def test_failed_mutation_gets_conservative_terminal_message():
    message = build_system_assistant_terminal_message([_entry("input_text", "error")])

    assert message.startswith("I couldn't complete")


def test_backend_and_android_both_implement_provisional_response_reset():
    runner = (BACKEND_DIR / "agent_runner.py").read_text(encoding="utf-8")
    bridge = (
        ROOT
        / "android/app/src/main/java/com/aetheria/ai/AssistantMobileBridgeManager.java"
    ).read_text(encoding="utf-8")
    session = (
        ROOT
        / "android/app/src/main/java/com/aetheria/ai/AssistantSession.java"
    ).read_text(encoding="utf-8")

    assert 'socketio.emit("assistant_response_reset"' in runner
    assert 'socket.on("assistant_response_reset"' in bridge
    assert "onAssistantResponseReset" in session


def test_stream_runner_captures_agent_completed_event_metrics():
    runner = (BACKEND_DIR / "agent_runner.py").read_text(encoding="utf-8")

    assert "RunEvent.run_completed.value" in runner
    assert "getattr(chunk, \"metrics\", None)" in runner
    assert "Captured completed Agno output/event" in runner

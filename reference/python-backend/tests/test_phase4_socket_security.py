import ast
import json
import sys
import types
from pathlib import Path

try:
    import redis  # noqa: F401
except ModuleNotFoundError:
    redis_stub = types.ModuleType("redis")
    redis_stub.Redis = object
    sys.modules["redis"] = redis_stub

from run_state_manager import RunStateManager
from socket_security import (
    can_access_conversation,
    get_conversation_owner,
    safe_socket_message_metadata,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]


class FakeRedis:
    def __init__(self):
        self.values = {}

    def set(self, key, value, ex=None):
        self.values[key] = value

    def get(self, key):
        return self.values.get(key)

    def delete(self, *keys):
        for key in keys:
            self.values.pop(key, None)


class FakeConnectionManager:
    def __init__(self, session=None):
        self.session = session

    def get_session(self, _conversation_id):
        return self.session


class FakeRunStateManager:
    def __init__(self, state=None):
        self.state = state

    def get_state(self, _conversation_id):
        return self.state


def test_socket_log_metadata_never_contains_token_or_message():
    metadata = safe_socket_message_metadata(
        {
            "accessToken": "secret.jwt.value",
            "message": "private user prompt",
            "conversationId": "conversation-123",
            "id": "message-456",
            "config": {"private": "value"},
        }
    )

    serialized = json.dumps(metadata)
    assert "secret.jwt.value" not in serialized
    assert "private user prompt" not in serialized
    assert metadata == {
        "conversation_id": "conversation-123",
        "message_id": "message-456",
        "message_length": 19,
        "has_access_token": True,
    }

    hostile = safe_socket_message_metadata(
        {"conversationId": "conv\nforged-log-entry", "id": "x" * 300}
    )
    assert "\n" not in hostile["conversation_id"]
    assert len(hostile["message_id"]) <= 128


def test_conversation_owner_prefers_live_session_then_run_state():
    assert get_conversation_owner(
        "conversation-123",
        FakeConnectionManager({"user_id": "session-owner"}),
        FakeRunStateManager({"user_id": "run-owner"}),
    ) == "session-owner"

    assert get_conversation_owner(
        "conversation-123",
        FakeConnectionManager(),
        FakeRunStateManager({"user_id": "run-owner"}),
    ) == "run-owner"


def test_existing_conversation_is_only_accessible_to_its_owner():
    manager = FakeConnectionManager({"user_id": "owner"})
    run_state = FakeRunStateManager()

    assert can_access_conversation("owner", "conversation-123", manager, run_state)
    assert not can_access_conversation("attacker", "conversation-123", manager, run_state)


def test_new_conversation_can_be_created_but_cannot_be_joined_for_catchup():
    manager = FakeConnectionManager()
    run_state = FakeRunStateManager()

    assert can_access_conversation(
        "owner",
        "conversation-123",
        manager,
        run_state,
        allow_unowned=True,
    )
    assert not can_access_conversation(
        "owner",
        "conversation-123",
        manager,
        run_state,
        allow_unowned=False,
    )


def test_completed_and_failed_run_state_preserve_owner():
    redis = FakeRedis()
    manager = RunStateManager(redis)

    manager.start_run("conversation-123", "message-1", "owner")
    manager.complete_run("conversation-123", "message-1", final_content="done")
    assert manager.get_state("conversation-123")["user_id"] == "owner"

    manager.start_run("conversation-123", "message-2", "owner")
    manager.fail_run("conversation-123", "message-2", "failed")
    assert manager.get_state("conversation-123")["user_id"] == "owner"


def test_system_assistant_is_configured_for_persistent_history():
    tree = ast.parse((BACKEND_DIR / "system_assistant.py").read_text(encoding="utf-8"))
    source = (BACKEND_DIR / "system_assistant.py").read_text(encoding="utf-8")

    assert "PostgresDb" in source
    assert "add_history_to_context=True" in source
    assert "num_history_runs=" in source
    assert any(
        isinstance(node, ast.keyword) and node.arg == "user_id"
        for node in ast.walk(tree)
    )


def test_agent_runner_captures_agent_and_team_run_outputs():
    source = (BACKEND_DIR / "agent_runner.py").read_text(encoding="utf-8")

    assert "RunOutput" in source
    assert "isinstance(chunk, (RunOutput, TeamRunOutput))" in source
    assert ".maybe_single()" in source


def test_assistant_socket_does_not_log_raw_payload():
    source = (BACKEND_DIR / "sockets.py").read_text(encoding="utf-8")

    assert 'Received message: {data}' not in source
    assert "safe_socket_message_metadata(data)" in source


def test_agno_debug_logging_is_opt_in():
    config_source = (BACKEND_DIR / "config.py").read_text(encoding="utf-8")
    runner_source = (BACKEND_DIR / "agent_runner.py").read_text(encoding="utf-8")

    assert 'os.getenv("AGNO_DEBUG_MODE", "false")' in config_source
    assert "debug_mode=config.AGNO_DEBUG_MODE" in runner_source

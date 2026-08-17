from __future__ import annotations

from unittest.mock import patch

from pipeline.services.convex_service import (
    ConvexMirroringPostgresDbMixin,
    ConvexService,
)


class _FakeConvexClient:
    def __init__(self) -> None:
        self.mutations = []

    def mutation(self, name, args):
        self.mutations.append((name, args))
        return {"ok": True}


def test_agno_session_and_runs_are_chunked_and_mirrored():
    client = _FakeConvexClient()
    session = {
        "session_id": "session-1",
        "agent_id": "stock-agent",
        "user_id": "supabase-user-1",
        "created_at": 1,
        "updated_at": 2,
        "metadata": {"symbol": "TEST"},
        "runs": [
            {
                "run_id": "run-1",
                "status": "COMPLETED",
                "content": "analysis complete",
                "created_at": 1,
            }
        ],
    }

    ConvexService._mirrored_hashes = {}
    with patch.object(ConvexService, "client", return_value=client):
        ConvexService.mirror_session(session)

    assert [name for name, _ in client.mutations] == [
        "agentSessions:replaceSession",
        "agentSessions:replaceRun",
    ]
    session_args = client.mutations[0][1]
    run_args = client.mutations[1][1]
    assert session_args["userId"] == "supabase-user-1"
    assert session_args["runCount"] == 1
    assert run_args["runId"] == "run-1"
    assert run_args["contentPreview"] == "analysis complete"
    assert "runs" not in "".join(session_args["payloadChunks"])


def test_mirror_mixin_preserves_native_agno_write_then_mirrors():
    events = []

    class NativeDb:
        def upsert_session(self, session, deserialize=True):
            events.append("postgres")
            return session

    class MirroredDb(ConvexMirroringPostgresDbMixin, NativeDb):
        pass

    with patch.object(ConvexService, "mirror_session", side_effect=lambda _: events.append("convex")):
        result = MirroredDb().upsert_session({"session_id": "session-1"})

    assert result == {"session_id": "session-1"}
    assert events == ["postgres", "convex"]

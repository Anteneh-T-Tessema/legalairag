"""Unit tests for agents.base_agent — BaseAgent, AgentRun, audit persistence."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import AgentRun, BaseAgent, _serialise_run


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Concrete test agent ──────────────────────────────────────────────────────


class _TestAgent(BaseAgent):
    allowed_tools = ["search", "retrieve"]

    def __init__(self, result: Any = "ok", error: Exception | None = None) -> None:
        super().__init__()
        self._result = result
        self._error = error

    async def _execute(self, **kwargs: Any) -> Any:
        if self._error:
            raise self._error
        return self._result


# ── BaseAgent.run ─────────────────────────────────────────────────────────────


class TestBaseAgentRun:
    def test_successful_run_returns_result(self) -> None:
        agent = _TestAgent(result="answer")
        result = _run(agent.run(query="test"))
        assert result == "answer"

    def test_run_sets_run_id(self) -> None:
        agent = _TestAgent()
        _run(agent.run())
        assert agent._run_id != ""

    def test_failing_run_raises(self) -> None:
        agent = _TestAgent(error=ValueError("boom"))
        with pytest.raises(ValueError, match="boom"):
            _run(agent.run())


# ── _record_tool_call ────────────────────────────────────────────────────────


class TestRecordToolCall:
    def test_allowed_tool_recorded(self) -> None:
        agent = _TestAgent()
        agent._record_tool_call("search", {"query": "test"})
        assert len(agent._tool_log) == 1
        assert agent._tool_log[0]["tool"] == "search"

    def test_disallowed_tool_raises(self) -> None:
        agent = _TestAgent()
        with pytest.raises(PermissionError, match="not permitted"):
            agent._record_tool_call("delete_everything", {})


# ── _serialise_run ───────────────────────────────────────────────────────────


class TestSerialiseRun:
    def test_dates_are_iso_strings(self) -> None:
        now = datetime.now(tz=timezone.utc)
        run = AgentRun(
            run_id="r1",
            agent_name="TestAgent",
            input_summary="in",
            output_summary="out",
            tool_calls=[],
            started_at=now,
            finished_at=now,
            success=True,
        )
        d = _serialise_run(run)
        assert isinstance(d["started_at"], str)
        assert isinstance(d["finished_at"], str)
        # Should be JSON-serialisable
        json.dumps(d, default=str)


# ── _write_audit_log ─────────────────────────────────────────────────────────


class TestWriteAuditLog:
    @patch("agents.base_agent.settings")
    def test_fallback_to_structured_log_when_no_bucket(self, mock_settings: MagicMock) -> None:
        mock_settings.audit_s3_bucket = ""
        agent = _TestAgent()
        now = datetime.now(tz=timezone.utc)
        run = AgentRun(
            run_id="r1",
            agent_name="TestAgent",
            input_summary="in",
            output_summary="out",
            tool_calls=[],
            started_at=now,
            finished_at=now,
            success=True,
        )
        # Should not raise — falls back to logger.info
        _run(agent._write_audit_log(run))

    @patch("agents.base_agent.settings")
    def test_s3_write_attempted_when_bucket_set(self, mock_settings: MagicMock) -> None:
        mock_settings.audit_s3_bucket = "my-audit-bucket"
        agent = _TestAgent()
        now = datetime.now(tz=timezone.utc)
        run = AgentRun(
            run_id="r1",
            agent_name="TestAgent",
            input_summary="in",
            output_summary="out",
            tool_calls=[],
            started_at=now,
            finished_at=now,
            success=True,
        )
        mock_client = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_ctx.__aexit__.return_value = False

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ctx

        # Create a mock aioboto3 module and inject it into agents.base_agent
        import types

        fake_aioboto3 = types.ModuleType("aioboto3")
        fake_aioboto3.Session = MagicMock(return_value=mock_session)  # type: ignore[attr-defined]

        import sys

        sys.modules["aioboto3"] = fake_aioboto3
        try:
            _run(agent._write_audit_log(run))
            mock_client.put_object.assert_awaited_once()
        finally:
            del sys.modules["aioboto3"]

    @patch("agents.base_agent.settings")
    def test_s3_write_exception_falls_back_to_log(self, mock_settings: MagicMock) -> None:
        """When put_object raises, the except block logs a warning and falls back."""
        mock_settings.audit_s3_bucket = "my-audit-bucket"
        agent = _TestAgent()
        now = datetime.now(tz=timezone.utc)
        run = AgentRun(
            run_id="r2",
            agent_name="TestAgent",
            input_summary="in",
            output_summary="out",
            tool_calls=[],
            started_at=now,
            finished_at=now,
            success=True,
        )
        mock_client = AsyncMock()
        mock_client.put_object.side_effect = Exception("S3 unavailable")
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_ctx.__aexit__.return_value = False

        mock_session = MagicMock()
        mock_session.client.return_value = mock_ctx

        import types
        import sys

        fake_aioboto3 = types.ModuleType("aioboto3")
        fake_aioboto3.Session = MagicMock(return_value=mock_session)  # type: ignore[attr-defined]

        sys.modules["aioboto3"] = fake_aioboto3
        try:
            # Should not raise — falls back to logger.info after warning
            _run(agent._write_audit_log(run))
        finally:
            del sys.modules["aioboto3"]

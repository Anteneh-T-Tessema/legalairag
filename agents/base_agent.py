from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AgentRun:
    """Immutable audit record for a single agent execution."""

    run_id: str
    agent_name: str
    input_summary: str
    output_summary: str
    tool_calls: list[dict[str, Any]]
    started_at: datetime
    finished_at: datetime
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """
    Base class for all IndyLeg agents.

    Contract:
    - Every agent action is logged with a unique run_id (audit trail).
    - Tool access is explicitly declared via `allowed_tools`.
    - Agents call `_record_tool_call` before invoking any external tool.
    - On completion (success or failure), an AgentRun is persisted.

    Government context: every automated legal decision must be fully
    traceable — this base class enforces that at the framework level.
    """

    allowed_tools: list[str] = []  # subclasses declare permitted tools

    def __init__(self) -> None:
        self._tool_log: list[dict[str, Any]] = []
        self._run_id: str = ""
        self._started_at: datetime | None = None

    async def run(self, **kwargs: Any) -> Any:
        self._run_id = str(uuid.uuid4())
        self._started_at = datetime.now(tz=timezone.utc)
        self._tool_log = []

        logger.info(
            "agent_start",
            agent=self.__class__.__name__,
            run_id=self._run_id,
        )

        try:
            result = await self._execute(**kwargs)
            await self._persist_run(
                input_summary=str(kwargs)[:200],
                output_summary=str(result)[:200],
                success=True,
            )
            return result
        except Exception as exc:
            await self._persist_run(
                input_summary=str(kwargs)[:200],
                output_summary="",
                success=False,
                error=str(exc),
            )
            logger.error(
                "agent_failure",
                agent=self.__class__.__name__,
                run_id=self._run_id,
                error=str(exc),
                exc_info=True,
            )
            raise

    @abstractmethod
    async def _execute(self, **kwargs: Any) -> Any:
        """Subclasses implement their agent logic here."""

    def _record_tool_call(self, tool: str, inputs: dict[str, Any]) -> None:
        if tool not in self.allowed_tools:
            raise PermissionError(
                f"Agent {self.__class__.__name__} is not permitted to use tool '{tool}'"
            )
        self._tool_log.append(
            {
                "tool": tool,
                "inputs": inputs,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }
        )

    async def _persist_run(
        self,
        input_summary: str,
        output_summary: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        run = AgentRun(
            run_id=self._run_id,
            agent_name=self.__class__.__name__,
            input_summary=input_summary,
            output_summary=output_summary,
            tool_calls=list(self._tool_log),
            started_at=self._started_at or datetime.now(tz=timezone.utc),
            finished_at=datetime.now(tz=timezone.utc),
            success=success,
            error=error,
        )
        # TODO: persist `run` to a audit log store (DynamoDB / RDS table)
        logger.info(
            "agent_run_complete",
            run_id=run.run_id,
            agent=run.agent_name,
            success=run.success,
            tool_calls=len(run.tool_calls),
            duration_ms=int((run.finished_at - run.started_at).total_seconds() * 1000),
        )

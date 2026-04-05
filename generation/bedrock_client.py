from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import boto3
from botocore.config import Config

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

_CONFIG = Config(
    region_name=settings.aws_region,
    retries={"max_attempts": 3, "mode": "adaptive"},
)


class BedrockLLMClient:
    """
    Thin wrapper around the AWS Bedrock Runtime converse API (Claude).

    Supports:
    - Single-turn completion
    - Streaming response (token-by-token)
    - System prompt injection

    Keeps Bedrock-specific JSON shapes isolated from the rest of the codebase.
    """

    def __init__(
        self,
        model_id: str = settings.bedrock_llm_model,
        max_tokens: int = settings.bedrock_max_tokens,
    ) -> None:
        self._model_id = model_id
        self._max_tokens = max_tokens
        self._client = boto3.client("bedrock-runtime", config=_CONFIG)

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        stop_sequences: list[str] | None = None,
    ) -> str:
        """
        Synchronous completion using the Bedrock Converse API.
        temperature=0.0 for deterministic, auditable legal outputs.
        """
        converse_messages = [
            {"role": msg["role"], "content": [{"text": msg["content"]}]} for msg in messages
        ]

        kwargs: dict[str, Any] = {
            "modelId": self._model_id,
            "system": [{"text": system}],
            "messages": converse_messages,
            "inferenceConfig": {
                "maxTokens": self._max_tokens,
                "temperature": temperature,
            },
        }
        if stop_sequences:
            kwargs["inferenceConfig"]["stopSequences"] = stop_sequences

        try:
            response = self._client.converse(**kwargs)
        except Exception:
            if settings.app_env == "development":
                logger.warning("bedrock_llm_unavailable_dev_fallback")
                return self._dev_fallback(messages)
            raise
        content = response["output"]["message"]["content"]
        text = "".join(block["text"] for block in content if "text" in block)

        logger.info(
            "bedrock_complete",
            model=self._model_id,
            input_tokens=response["usage"]["inputTokens"],
            output_tokens=response["usage"]["outputTokens"],
        )
        return text

    @staticmethod
    def _dev_fallback(messages: list[dict[str, str]]) -> str:
        """Return a context-aware answer synthesised from the user prompt's context chunks."""
        user_text = messages[-1]["content"] if messages else ""
        import re

        # Match the prompt template format: [N] SOURCE: ... | SECTION: ...\nCitations: ...\ncontent
        blocks = re.findall(
            r"\[(\d+)\]\s*SOURCE:\s*([^\n|]+)\|\s*SECTION:\s*([^\n]*)\n"
            r"Citations:\s*([^\n]*)\n(.*?)(?=\n---\n|\nProvide|\Z)",
            user_text,
            re.DOTALL,
        )

        if blocks:
            parts = []
            for idx, source_id, section, citations, content in blocks[:6]:
                content_clean = content.strip()[:400]
                parts.append(
                    f"**[{idx}] {section.strip()}** ({source_id.strip()})\n"
                    f"Citations: {citations.strip()}\n"
                    f"{content_clean}"
                )
            summary = "\n\n---\n\n".join(parts)
            return (
                f"**[DEV MODE — no LLM available; showing retrieved context]**\n\n"
                f"Based on the retrieved documents:\n\n{summary}\n\n"
                f"*Note: In production, AWS Bedrock Claude would synthesise a "
                f"citation-grounded legal answer from these sources.*"
            )
        return (
            "**[DEV MODE]** No Bedrock LLM available. "
            "The retrieval pipeline returned results but generation requires "
            "AWS Bedrock credentials. Configure real AWS credentials to enable "
            "full RAG generation."
        )

    def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> Iterator[str]:
        """Streaming variant — yields text deltas as they arrive."""
        converse_messages = [
            {"role": msg["role"], "content": [{"text": msg["content"]}]} for msg in messages
        ]

        response = self._client.converse_stream(
            modelId=self._model_id,
            system=[{"text": system}],
            messages=converse_messages,
            inferenceConfig={
                "maxTokens": self._max_tokens,
                "temperature": temperature,
            },
        )

        for event in response["stream"]:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    yield delta["text"]

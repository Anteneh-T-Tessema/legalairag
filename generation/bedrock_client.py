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

        response = self._client.converse(**kwargs)
        content = response["output"]["message"]["content"]
        text = "".join(block["text"] for block in content if "text" in block)

        logger.info(
            "bedrock_complete",
            model=self._model_id,
            input_tokens=response["usage"]["inputTokens"],
            output_tokens=response["usage"]["outputTokens"],
        )
        return text

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

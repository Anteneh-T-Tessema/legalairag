"""Unit tests for generation.bedrock_client — BedrockLLMClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestBedrockLLMClient:
    def _make_client(self, converse_response=None, stream_response=None):
        with patch("generation.bedrock_client.boto3.client") as mock_boto:
            mock_bedrock = MagicMock()
            mock_boto.return_value = mock_bedrock

            if converse_response is None:
                converse_response = {
                    "output": {"message": {"content": [{"text": "The answer is 42."}]}},
                    "usage": {"inputTokens": 100, "outputTokens": 50},
                }
            mock_bedrock.converse.return_value = converse_response

            if stream_response:
                mock_bedrock.converse_stream.return_value = stream_response

            from generation.bedrock_client import BedrockLLMClient

            client = BedrockLLMClient.__new__(BedrockLLMClient)
            client._model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
            client._max_tokens = 4096
            client._client = mock_bedrock
            return client, mock_bedrock

    def test_complete_returns_text(self):
        client, _ = self._make_client()
        result = client.complete(
            system="You are a legal assistant.",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert result == "The answer is 42."

    def test_complete_calls_converse_with_correct_params(self):
        client, mock_bedrock = self._make_client()
        client.complete(
            system="System prompt",
            messages=[{"role": "user", "content": "Query"}],
            temperature=0.5,
        )

        call_kwargs = mock_bedrock.converse.call_args[1]
        assert call_kwargs["modelId"] == client._model_id
        assert call_kwargs["system"] == [{"text": "System prompt"}]
        assert call_kwargs["inferenceConfig"]["temperature"] == 0.5
        assert call_kwargs["inferenceConfig"]["maxTokens"] == 4096

    def test_complete_passes_stop_sequences(self):
        client, mock_bedrock = self._make_client()
        client.complete(
            system="sys",
            messages=[{"role": "user", "content": "q"}],
            stop_sequences=["STOP"],
        )
        call_kwargs = mock_bedrock.converse.call_args[1]
        assert call_kwargs["inferenceConfig"]["stopSequences"] == ["STOP"]

    def test_complete_without_stop_sequences(self):
        client, mock_bedrock = self._make_client()
        client.complete(
            system="sys",
            messages=[{"role": "user", "content": "q"}],
        )
        call_kwargs = mock_bedrock.converse.call_args[1]
        assert "stopSequences" not in call_kwargs["inferenceConfig"]

    def test_complete_concatenates_multiple_content_blocks(self):
        resp = {
            "output": {"message": {"content": [{"text": "Part 1. "}, {"text": "Part 2."}]}},
            "usage": {"inputTokens": 50, "outputTokens": 30},
        }
        client, _ = self._make_client(converse_response=resp)
        result = client.complete(
            system="sys",
            messages=[{"role": "user", "content": "q"}],
        )
        assert result == "Part 1. Part 2."

    def test_stream_yields_text_deltas(self):
        stream_resp = {
            "stream": [
                {"contentBlockDelta": {"delta": {"text": "Hello "}}},
                {"contentBlockDelta": {"delta": {"text": "world"}}},
                {"messageStop": {}},
            ]
        }
        client, mock_bedrock = self._make_client(stream_response=stream_resp)
        mock_bedrock.converse_stream.return_value = stream_resp

        chunks = list(
            client.stream(
                system="sys",
                messages=[{"role": "user", "content": "q"}],
            )
        )
        assert chunks == ["Hello ", "world"]

    def test_stream_skips_non_text_events(self):
        stream_resp = {
            "stream": [
                {"contentBlockStart": {}},
                {"contentBlockDelta": {"delta": {"text": "data"}}},
                {"contentBlockStop": {}},
            ]
        }
        client, mock_bedrock = self._make_client(stream_response=stream_resp)
        mock_bedrock.converse_stream.return_value = stream_resp

        chunks = list(
            client.stream(
                system="sys",
                messages=[{"role": "user", "content": "q"}],
            )
        )
        assert chunks == ["data"]

    def test_complete_formats_messages_correctly(self):
        client, mock_bedrock = self._make_client()
        client.complete(
            system="sys",
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
            ],
        )
        call_kwargs = mock_bedrock.converse.call_args[1]
        assert call_kwargs["messages"] == [
            {"role": "user", "content": [{"text": "Hello"}]},
            {"role": "assistant", "content": [{"text": "Hi"}]},
        ]

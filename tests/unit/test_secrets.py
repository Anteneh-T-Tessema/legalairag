"""Unit tests for config.secrets — SSM, Secrets Manager, resolve_secret."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

# ── resolve_ssm_parameter ─────────────────────────────────────────────────────


class TestResolveSSMParameter:
    def setup_method(self):
        # Clear lru_cache between tests
        from config.secrets import resolve_ssm_parameter

        resolve_ssm_parameter.cache_clear()

    def test_returns_parameter_value(self):
        from config.secrets import resolve_ssm_parameter

        mock_client = MagicMock()
        mock_client.get_parameter.return_value = {"Parameter": {"Value": "my-secret"}}
        with patch("config.secrets.boto3.client", return_value=mock_client):
            result = resolve_ssm_parameter("/indyleg/prod/db_password")
            assert result == "my-secret"
            mock_client.get_parameter.assert_called_once_with(
                Name="/indyleg/prod/db_password", WithDecryption=True
            )

    def test_returns_none_on_not_found(self):
        from config.secrets import resolve_ssm_parameter

        mock_client = MagicMock()
        mock_client.get_parameter.side_effect = ClientError(
            {"Error": {"Code": "ParameterNotFound", "Message": "nope"}},
            "GetParameter",
        )
        with patch("config.secrets.boto3.client", return_value=mock_client):
            assert resolve_ssm_parameter("/missing/param") is None

    def test_returns_none_on_other_client_error(self):
        from config.secrets import resolve_ssm_parameter

        mock_client = MagicMock()
        mock_client.get_parameter.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "boom"}},
            "GetParameter",
        )
        with patch("config.secrets.boto3.client", return_value=mock_client):
            assert resolve_ssm_parameter("/failing/param") is None

    def test_decrypt_false(self):
        from config.secrets import resolve_ssm_parameter

        mock_client = MagicMock()
        mock_client.get_parameter.return_value = {"Parameter": {"Value": "plain"}}
        with patch("config.secrets.boto3.client", return_value=mock_client):
            result = resolve_ssm_parameter("/non-secret", decrypt=False)
            assert result == "plain"
            mock_client.get_parameter.assert_called_once_with(
                Name="/non-secret", WithDecryption=False
            )


# ── resolve_secrets_manager ───────────────────────────────────────────────────


class TestResolveSecretsManager:
    def setup_method(self):
        from config.secrets import resolve_secrets_manager

        resolve_secrets_manager.cache_clear()

    def test_returns_parsed_dict(self):
        from config.secrets import resolve_secrets_manager

        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": '{"username": "admin", "password": "s3cret"}'
        }
        with patch("config.secrets.boto3.client", return_value=mock_client):
            result = resolve_secrets_manager("indyleg/db-creds")
            assert result == {"username": "admin", "password": "s3cret"}

    def test_returns_none_on_client_error(self):
        from config.secrets import resolve_secrets_manager

        mock_client = MagicMock()
        mock_client.get_secret_value.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}},
            "GetSecretValue",
        )
        with patch("config.secrets.boto3.client", return_value=mock_client):
            assert resolve_secrets_manager("missing/secret") is None

    def test_returns_none_on_invalid_json(self):
        from config.secrets import resolve_secrets_manager

        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "not json"}
        with patch("config.secrets.boto3.client", return_value=mock_client):
            assert resolve_secrets_manager("bad-json-secret") is None


# ── resolve_secret (cascading fallback) ───────────────────────────────────────


class TestResolveSecret:
    def setup_method(self):
        from config.secrets import resolve_secrets_manager, resolve_ssm_parameter

        resolve_ssm_parameter.cache_clear()
        resolve_secrets_manager.cache_clear()

    def test_returns_ssm_first(self):
        from config.secrets import resolve_secret

        with patch("config.secrets.resolve_ssm_parameter", return_value="ssm-val"):
            result = resolve_secret("/path", fallback="fb")
            assert result == "ssm-val"

    def test_falls_back_to_secrets_manager(self):
        from config.secrets import resolve_secret

        with (
            patch("config.secrets.resolve_ssm_parameter", return_value=None),
            patch(
                "config.secrets.resolve_secrets_manager",
                return_value={"db_password": "sm-val"},
            ),
        ):
            result = resolve_secret(
                "/missing",
                secrets_manager_id="indyleg/creds",
                secrets_manager_key="db_password",
                fallback="fb",
            )
            assert result == "sm-val"

    def test_falls_back_to_default(self):
        from config.secrets import resolve_secret

        with (
            patch("config.secrets.resolve_ssm_parameter", return_value=None),
            patch("config.secrets.resolve_secrets_manager", return_value=None),
        ):
            result = resolve_secret(
                "/missing",
                secrets_manager_id="missing/id",
                secrets_manager_key="key",
                fallback="default-value",
            )
            assert result == "default-value"

    def test_no_ssm_path_skips_to_sm(self):
        from config.secrets import resolve_secret

        with patch(
            "config.secrets.resolve_secrets_manager",
            return_value={"key": "val"},
        ):
            result = resolve_secret(
                None,
                secrets_manager_id="id",
                secrets_manager_key="key",
            )
            assert result == "val"

    def test_empty_fallback_default(self):
        from config.secrets import resolve_secret

        with patch("config.secrets.resolve_ssm_parameter", return_value=None):
            result = resolve_secret("/missing")
            assert result == ""

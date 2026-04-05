"""Unit tests for config.settings — Settings + _resolve_production_secrets."""

from __future__ import annotations

from unittest.mock import patch


class TestSettings:
    def test_default_app_env(self):
        from config.settings import Settings

        s = Settings()
        assert s.app_env == "development"

    def test_default_aws_region(self):
        from config.settings import Settings

        s = Settings()
        assert s.aws_region == "us-east-1"

    def test_hmac_key_at_least_32_bytes(self):
        from config.settings import Settings

        s = Settings()
        assert len(s.api_secret_key.get_secret_value()) >= 32

    def test_default_bedrock_models(self):
        from config.settings import Settings

        s = Settings()
        assert "titan-embed" in s.bedrock_embedding_model
        assert "claude" in s.bedrock_llm_model


class TestResolveProductionSecrets:
    def test_skips_in_development(self):
        from config.settings import Settings, _resolve_production_secrets

        s = Settings(app_env="development", ssm_prefix="/indyleg/prod")
        result = _resolve_production_secrets(s)
        # Should not change anything
        assert result.database_url == s.database_url

    def test_skips_without_ssm_prefix(self):
        from config.settings import Settings, _resolve_production_secrets

        s = Settings(app_env="production", ssm_prefix="")
        result = _resolve_production_secrets(s)
        assert result.database_url == s.database_url

    def test_resolves_database_url(self):
        from config.settings import Settings, _resolve_production_secrets

        s = Settings(app_env="production", ssm_prefix="/indyleg/prod")
        with patch("config.secrets.resolve_secret") as mock_resolve:
            mock_resolve.side_effect = lambda path, fallback="": (
                "postgresql://prod:pass@db:5432/indyleg" if "database_url" in path else ""
            )
            result = _resolve_production_secrets(s)
            assert "prod:pass" in result.database_url

    def test_resolves_api_secret_key(self):
        from config.settings import Settings, _resolve_production_secrets

        s = Settings(app_env="staging", ssm_prefix="/indyleg/staging")
        with patch("config.secrets.resolve_secret") as mock_resolve:
            mock_resolve.side_effect = lambda path, fallback="": (
                "super-secret-production-key-1234" if "api_secret_key" in path else ""
            )
            result = _resolve_production_secrets(s)
            assert result.api_secret_key.get_secret_value() == "super-secret-production-key-1234"

    def test_resolves_courts_api_key(self):
        from config.settings import Settings, _resolve_production_secrets

        s = Settings(app_env="production", ssm_prefix="/indyleg/prod")
        with patch("config.secrets.resolve_secret") as mock_resolve:
            mock_resolve.side_effect = lambda path, fallback="": (
                "courts-api-key-xyz" if "indiana_courts_api_key" in path else ""
            )
            result = _resolve_production_secrets(s)
            assert result.indiana_courts_api_key == "courts-api-key-xyz"

    def test_resolves_courtlistener_token(self):
        from config.settings import Settings, _resolve_production_secrets

        s = Settings(app_env="production", ssm_prefix="/indyleg/prod")
        with patch("config.secrets.resolve_secret") as mock_resolve:
            mock_resolve.side_effect = lambda path, fallback="": (
                "cl-token-abc" if "courtlistener_api_token" in path else ""
            )
            result = _resolve_production_secrets(s)
            assert result.courtlistener_api_token == "cl-token-abc"

    def test_keeps_defaults_when_ssm_returns_empty(self):
        from config.settings import Settings, _resolve_production_secrets

        original_db = "postgresql+psycopg://indyleg:changeme@localhost:5432/indyleg"
        s = Settings(app_env="production", ssm_prefix="/indyleg/prod")
        with patch("config.secrets.resolve_secret", return_value=""):
            result = _resolve_production_secrets(s)
            assert result.database_url == original_db

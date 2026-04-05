"""Fetch secrets from AWS SSM Parameter Store or Secrets Manager.

In production/staging, sensitive settings (API keys, DB credentials) should be
stored in SSM Parameter Store (SecureString) or Secrets Manager and loaded at
startup.  In development, values fall back to env vars / .env file.

Usage:
    from config.secrets import resolve_secret
    db_password = resolve_secret("/indyleg/prod/database_password", fallback="changeme")
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=64)
def resolve_ssm_parameter(name: str, *, decrypt: bool = True) -> str | None:
    """Fetch a single parameter from SSM Parameter Store.

    Returns None if the parameter does not exist or the call fails.
    Results are cached for the lifetime of the process.
    """
    try:
        client = boto3.client("ssm")
        resp = client.get_parameter(Name=name, WithDecryption=decrypt)
        return resp["Parameter"]["Value"]
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code == "ParameterNotFound":
            logger.debug("SSM parameter %s not found", name)
        else:
            logger.warning("SSM lookup failed for %s: %s", name, exc)
        return None


@lru_cache(maxsize=16)
def resolve_secrets_manager(secret_id: str) -> dict[str, str] | None:
    """Fetch a JSON secret from AWS Secrets Manager.

    Returns the parsed dict or None on failure.  Results are cached.
    """
    try:
        client = boto3.client("secretsmanager")
        resp = client.get_secret_value(SecretId=secret_id)
        return json.loads(resp["SecretString"])
    except (ClientError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("Secrets Manager lookup failed for %s: %s", secret_id, exc)
        return None


def resolve_secret(
    ssm_path: str | None = None,
    *,
    secrets_manager_id: str | None = None,
    secrets_manager_key: str | None = None,
    fallback: str = "",
) -> str:
    """Resolve a secret value with cascading fallback.

    Priority:
      1. SSM Parameter Store (if ssm_path provided)
      2. Secrets Manager JSON key (if secrets_manager_id + key provided)
      3. fallback value
    """
    if ssm_path:
        value = resolve_ssm_parameter(ssm_path)
        if value is not None:
            return value

    if secrets_manager_id and secrets_manager_key:
        secret_dict = resolve_secrets_manager(secrets_manager_id)
        if secret_dict and secrets_manager_key in secret_dict:
            return secret_dict[secrets_manager_key]

    return fallback

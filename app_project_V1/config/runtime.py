"""Runtime configuration for customer-neutral deployments."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


@dataclass(frozen=True)
class RuntimeConfig:
    app_name: str
    app_display_name: str
    environment: str
    catalog: str
    default_schema: str
    warehouse_id: str | None
    logo_path: str | None


def get_runtime_config() -> RuntimeConfig:
    """Return app configuration derived from deployment environment variables."""
    app_name = _env("APP_NAME", "reference-data-app")
    app_display_name = _env("APP_DISPLAY_NAME", "Reference Data Manager")
    environment = _env("APP_ENV", "dev")

    catalog = _env("CATALOG_NAME")
    if catalog is None:
        catalog_prefix = _env("CATALOG_PREFIX", app_name.replace("-", "_"))
        catalog = f"{catalog_prefix}_{environment}"

    logo_path = _env("APP_LOGO_PATH")
    if logo_path:
        logo_path = str(Path(logo_path).expanduser())

    return RuntimeConfig(
        app_name=app_name,
        app_display_name=app_display_name,
        environment=environment,
        catalog=catalog,
        default_schema=_env("DEFAULT_SCHEMA", "default"),
        warehouse_id=_env("DATABRICKS_WAREHOUSE_ID"),
        logo_path=logo_path,
    )


def require_warehouse_id() -> str:
    """Return the configured SQL warehouse ID or raise a deployment-focused error."""
    warehouse_id = get_runtime_config().warehouse_id
    if warehouse_id:
        return warehouse_id

    message = (
        "DATABRICKS_WAREHOUSE_ID is required. Configure it per customer and "
        "environment in Databricks Apps or the deployment pipeline."
    )
    raise RuntimeError(message)

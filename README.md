# Reference Data App

Reference Data App is a customer-neutral Streamlit application for browsing,
validating, submitting, reviewing, and publishing reference-data changes stored
in Databricks Unity Catalog and Delta tables.

It runs inside Databricks Apps and connects to Databricks SQL as the signed-in
user.

## What The App Does

- Browse the latest snapshot of a reference-data table.
- Add, edit, delete, or bulk upload rows.
- Publish changes as append-only snapshots using `__VERSION`.
- Optionally require review and approval before publishing.
- Run across customers, subscriptions, workspaces, catalogs, and environments
  through deployment configuration.

## Core Concepts

- Changes are published as new full-table snapshots rather than in-place updates.
- The app shows the latest snapshot view for the most recent `__VERSION`.
- Some tables can require review before changes are published.
- Catalog, schema, warehouse, app name, and display name are supplied by runtime
  configuration.

## Quick Start

1. Create or identify a Databricks SQL warehouse.
2. Create the target Unity Catalog catalog and schemas.
3. Configure the required runtime variables described in [docs/configuration.md](docs/configuration.md).
4. Deploy the app to Databricks Apps.
5. Open the app, select a schema and table, then use the Data Entry tab.

## Documentation

- [Getting started](docs/getting-started.md)
- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [Deployment](docs/deployment.md)
- [Operations](docs/operations.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Data entry and versioning](docs/features/data-entry-and-versioning.md)
- [Review and approval](docs/features/review-and-approval.md)
- [Table properties reference](docs/reference/table-properties.md)

## Repository Layout

- `app.py` orchestrates app startup, metadata loading, navigation, and feature panels.
- `ui/` contains Streamlit UI components.
- `config/` contains runtime configuration, constants, setup helpers, and metadata loading.
- `utils/` contains SQL access, data helpers, validation, and review workflow utilities.
- `styles/` contains neutral shared styling.

## Runtime Notes

- The app expects the Databricks Apps `x-forwarded-access-token` header when it talks to Databricks SQL.
- `DATABRICKS_WAREHOUSE_ID` must be configured per customer/environment.
- Set `CATALOG_NAME` directly, or set `CATALOG_PREFIX` and `APP_ENV` to derive the catalog.
- The deployment helper writes these values into the deployed `app.yaml`.

## Related Guides

- Use [docs/deployment.md](docs/deployment.md) for Databricks Apps deployment.
- Use [docs/configuration.md](docs/configuration.md) for runtime configuration.
- Use [docs/features/review-and-approval.md](docs/features/review-and-approval.md) for the change request workflow.

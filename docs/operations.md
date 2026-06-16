# Operations

This guide documents the metadata objects, permissions, and operational checks needed to run the app safely.

## Managed Objects

### Reference Data Tables

Business data lives in Unity Catalog tables that follow the snapshot and audit-column conventions described in [architecture.md](architecture.md).

### Metadata Objects For Review

When review is enabled, the app manages:

- metadata schema: `{catalog}.app_metadata`
- change request table: `{catalog}.app_metadata.change_requests`
- per-table staging tables: `{target_table}_staging`

These objects are created on demand by the app when permissions allow it.

## Permissions

At minimum, the runtime user population needs:

- permission to use the target SQL warehouse
- permission to read the target catalog and schemas
- permission to read and insert into target tables

For review-enabled tables, the relevant users also need:

- permission to create the metadata schema if it does not already exist
- permission to create staging tables for review-enabled target tables
- permission to read and update change request metadata

## Reviewer Responsibilities

- review pending submissions before they reach production tables
- approve or reject requests submitted by other users
- avoid direct table-side fixes that bypass the audit trail unless absolutely necessary

The UI blocks self-approval and self-rejection for pending requests.

## Operational Checks

### Verify Metadata Schema

```sql
SHOW SCHEMAS IN ${CATALOG_NAME} LIKE 'app_metadata';
```

### Verify Change Request Table

```sql
DESCRIBE TABLE ${CATALOG_NAME}.app_metadata.change_requests;
```

### Verify Staging Tables

```sql
SHOW TABLES IN ${CATALOG_NAME}.${DEFAULT_SCHEMA} LIKE '*_staging';
```

## Data Retention

- Reference tables keep version history by appending snapshots.
- Change request metadata is retained for auditability.
- Staging rows are retained as part of the review trail unless removed manually.

If you add cleanup procedures, treat them as audited maintenance tasks rather than routine user actions.

## Operational Caveats

- Internal tables such as `_staging` tables are intentionally hidden from the regular table selector.
- `DATABRICKS_WAREHOUSE_ID`, catalog, and schema are explicit deployment inputs; verify them during every customer rollout.
- The app depends on Databricks Apps request headers for authenticated SQL access.

## Related Guides

- Review workflow: [features/review-and-approval.md](features/review-and-approval.md)
- Runtime behavior: [configuration.md](configuration.md)
- Failures and recovery: [troubleshooting.md](troubleshooting.md)

# Architecture

This document explains the app structure, execution flow, and data model.

## High-Level Flow

On each Streamlit rerun the app:

1. Configures the page and injects styles.
2. Triggers early Databricks connection setup so environment detection runs.
3. Builds the catalog name from the resolved environment.
4. Renders sidebar navigation for schema and table selection.
5. Loads table data, schema metadata, and table property constraints.
6. Renders the Data Entry tab.
7. Renders the Review & Approve tab if the selected table requires review.

## Main Modules

### Entry Point

- `app.py`: application bootstrap, layout, and top-level orchestration.

### Configuration And Metadata

- `config/setup.py`: page configuration and environment bootstrap.
- `config/constants.py`: audit column names and review workflow constants.
- `config/metadata.py`: data and metadata loading for the selected table.

### UI

- `ui/sidebar.py`: schema and table selection.
- `ui/hero.py`: page header.
- `ui/data_viewer.py`: latest snapshot view and row selection.
- `ui/actions.py`: single-row and bulk workflows.
- `ui/review_panel.py`: review queue, approve, and reject workflows.

### Utilities

- `utils/sql_utils.py`: Databricks SQL connectivity, data insertion, validation helpers, and table-property loading.
- `utils/data_utils.py`: cached data access and CSV parsing.
- `utils/review_utils.py`: metadata object creation, staging tables, and change request lifecycle.

## Data Model

The app assumes reference-data tables use append-only snapshot versioning with audit columns.

### Audit Columns

| Column | Meaning |
| --- | --- |
| `__KEY` | Row identifier |
| `__UPLOAD_TIMESTAMP` | Timestamp for the row-level write event |
| `__VERSION` | Snapshot version number |
| `__VERSION_TIMESTAMP` | Timestamp for the snapshot publish event |
| `__UPLOADED_BY` | User who submitted or published the row |
| `__UPLOAD_FILE_NAME` | Source marker for UI or bulk operations |

## Latest Snapshot Logic

When the UI shows table contents, it reads the table ordered by upload timestamp, filters to the latest `__VERSION`, and keeps the latest row per `__KEY` for display-oriented workflows.

## Publish Model

The app does not update rows in place.

- Single-row add or edit builds a new snapshot and inserts all rows with the next version.
- Delete removes selected keys from the latest snapshot and inserts the remaining rows as the next version.
- Bulk upload validates the CSV and inserts the resulting snapshot as the next version.

If review is enabled, the snapshot is staged as a change request instead of publishing immediately.

## Review Workflow Integration

Tables opt into review through the `review_required` Delta table property. When enabled, the UI shows a second tab for reviewers and routes submitted changes through staging and approval objects.

See [features/review-and-approval.md](features/review-and-approval.md) for the workflow and [operations.md](operations.md) for the underlying objects.

## Caching And Session State

### Cached Operations

- SQL connection: 10 minutes
- Table reads: 30 seconds
- Table list: 5 minutes
- CSV parsing: cached by file bytes and delimiter

### Important Session State Keys

- `selected_schema`
- `selected_table`
- `row_selection`
- `selected_row_for_copy`
- `prefill_token`
- `uploader_version`
- `nav_version`

## Internal Objects Hidden From The UI

The schema and table selectors intentionally hide internal helper objects such as:

- `app_metadata`
- tables ending in `_staging`
- tables ending in `_current`
- backup tables containing `_backup`

## Related Guides

- User workflows: [features/data-entry-and-versioning.md](features/data-entry-and-versioning.md)
- Review workflow: [features/review-and-approval.md](features/review-and-approval.md)
- Table properties: [reference/table-properties.md](reference/table-properties.md)
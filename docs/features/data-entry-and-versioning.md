# Data Entry And Versioning

This guide describes how the app presents reference data and how it publishes changes.

## Latest Snapshot View

The table viewer shows the latest logical state of the selected table, not the full history.

The displayed view is derived from the most recent `__VERSION`, with rows organized so that the latest record for each `__KEY` is used for interactive workflows.

## Supported Actions

### Single-Row Add Or Edit

Users can:

- create a new row
- load a selected row into the form
- edit editable fields
- submit the result directly or for review, depending on table configuration

### Delete Selected Rows

Users can select one or more rows and publish a new snapshot that excludes those keys.

### Bulk CSV Upload

Users can upload a CSV file, choose the delimiter, preview the cleaned data, and submit the resulting snapshot.

## Validation Rules

The app applies table-driven validation before publishing or submitting for review.

### Single-Row Validation

- required fields must not be empty
- values must match expected types where possible
- business keys must remain unique within the latest snapshot
- optional validity-window rules can prevent overlapping date ranges

### Bulk Validation

- required columns must be present
- required values must not be missing
- business keys must be unique within the file
- optional validity-window rules can detect overlaps inside the upload
- extra columns are ignored with a warning

The exact table-property switches are documented in [../reference/table-properties.md](../reference/table-properties.md).

## Publish Semantics

The app uses append-only snapshots.

### Direct Publish

If review is not required:

1. The app calculates the next `__VERSION` from the target table.
2. It builds the next full snapshot.
3. It inserts all snapshot rows with the new version.

### Review Required

If review is required:

1. The app builds the next full snapshot.
2. It writes the snapshot to the table-specific staging table.
3. It creates a change request record.
4. The snapshot is published only after approval.

## Audit Columns

The app manages these audit columns automatically:

- `__KEY`
- `__UPLOAD_TIMESTAMP`
- `__VERSION`
- `__VERSION_TIMESTAMP`
- `__UPLOADED_BY`
- `__UPLOAD_FILE_NAME`

## Related Guides

- Review workflow: [review-and-approval.md](review-and-approval.md)
- Architecture: [../architecture.md](../architecture.md)
- Table properties: [../reference/table-properties.md](../reference/table-properties.md)
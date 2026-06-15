# Table Properties Reference

This reference documents the Delta table properties that drive validation and UI behavior.

## Supported Properties

| Property | Type | Default | Effect |
| --- | --- | --- | --- |
| `not_null_columns` | comma-separated list | empty | Marks fields as required |
| `business_keys` | comma-separated list | empty | Enforces uniqueness for the logical snapshot |
| `not_editable` | comma-separated list | empty | Hides or locks fields in the single-row editor |
| `single_insert` | boolean | `true` | Enables or disables the single-row editor |
| `bulk_insert` | boolean | `true` | Enables or disables the bulk CSV workflow |
| `review_required` | boolean | `false` | Routes changes through review and approval |
| `valid_from` | column name | unset | Start column for validity-window checks |
| `valid_to` | column name | unset | End column for validity-window checks |
| `validity_key` | column name | unset | Grouping column for validity-window overlap checks |

## Notes On Parsing

- List properties are parsed as comma-separated values.
- Column names that do not exist in the table schema are ignored.
- Boolean properties are matched by comparing their lowercase string value to `true`.

## Audit Columns

These columns are treated as managed audit columns by the application:

- `__KEY`
- `__UPLOAD_TIMESTAMP`
- `__VERSION`
- `__VERSION_TIMESTAMP`
- `__UPLOADED_BY`
- `__UPLOAD_FILE_NAME`

## Review Workflow Constants

The review workflow adds:

- `__CR_ID` in staging tables
- `app_metadata.change_requests` as the metadata table

## Example

```sql
ALTER TABLE ${CATALOG_NAME}.${DEFAULT_SCHEMA}.example_table
SET TBLPROPERTIES (
  'not_null_columns' = 'code,name',
  'business_keys' = 'code',
  'single_insert' = 'true',
  'bulk_insert' = 'true',
  'review_required' = 'true',
  'valid_from' = 'valid_from',
  'valid_to' = 'valid_to',
  'validity_key' = 'code'
);
```

## Related Guides

- Data-entry behavior: [../features/data-entry-and-versioning.md](../features/data-entry-and-versioning.md)
- Review workflow: [../features/review-and-approval.md](../features/review-and-approval.md)
- Architecture: [../architecture.md](../architecture.md)

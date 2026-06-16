# Troubleshooting

This guide collects the most common runtime and deployment problems.

## App Fails With Missing Access Token

Symptom:

- errors mentioning `x-forwarded-access-token`
- SQL access fails immediately when loading data

Cause:

The app expects to run inside Databricks Apps and uses the Databricks Apps request header to connect as the signed-in user.

What to check:

- confirm the app is running inside Databricks Apps
- confirm the app has the required SQL authorization scope
- do not treat `streamlit run app.py` as a full local runtime path without additional mocking

## Wrong Environment Or Catalog Selected

Symptom:

- the app points at the wrong catalog
- the selected warehouse does not match the workspace

What to check:

- verify `CATALOG_NAME`, or verify `CATALOG_PREFIX` and `APP_ENV`
- verify `DATABRICKS_WAREHOUSE_ID`
- verify `DEFAULT_SCHEMA`
- confirm the Azure DevOps variable group belongs to the intended customer and environment

## No Schemas Or Tables Visible

Symptom:

- the sidebar is empty
- expected schemas or tables do not appear

What to check:

- verify Unity Catalog permissions for the current user
- verify the target schema is not filtered out as an internal schema
- verify the table is not an internal helper table such as `_staging`, `_current`, or `_backup`

## Review Objects Cannot Be Created

Symptom:

- review submission fails on first use
- errors mention schema or table creation

What to check:

- confirm create-schema permission for `{catalog}.app_metadata`
- confirm create-table permission for staging tables
- confirm the target table exists and is readable

## No Change Requests Visible

Symptom:

- the Review & Approve tab is present but no requests are shown

What to check:

- confirm the selected table has `review_required=true`
- confirm you are in the expected catalog and schema
- query `{catalog}.app_metadata.change_requests` directly to verify submissions exist

## App Starts But Shows Stale Data

The app caches the SQL connection, table reads, table lists, and CSV parsing.

What to try:

- use the refresh button in the data view
- rerun the app page
- wait for the relevant cache time-to-live to expire

## Deployment Problems

If deployment succeeds but the app does not start correctly:

- check Databricks Apps logs
- verify `requirements.txt` contains the required packages
- verify the deployed source path contains the current application files

## Related Guides

- Deployment: [deployment.md](deployment.md)
- Configuration: [configuration.md](configuration.md)
- Operations: [operations.md](operations.md)

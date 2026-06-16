# Getting Started

This guide covers the quickest path to using Reference Data App in a Databricks workspace.

## Prerequisites

- Databricks Apps must be enabled in the target workspace.
- You need access to the target Unity Catalog catalog and schemas.
- You need permission to use the configured SQL warehouse.
- If review is enabled for a table, reviewers need access to the metadata and staging objects described in [operations.md](operations.md).

## First-Time Setup

1. Deploy the app to Databricks Apps by following [deployment.md](deployment.md).
2. Open the app in the workspace where it was deployed.
3. The app connects to Databricks SQL using the configured warehouse and catalog.
4. Select a schema in the sidebar.
5. Select a table to browse or edit.

## Main User Flows

### Browse Current Data

Use the table view to inspect the latest snapshot for the selected table.

### Submit Data Changes

- Add or edit a single row in the form.
- Delete one or more selected rows.
- Upload a CSV file for bulk replacement of the latest snapshot.

Details are documented in [features/data-entry-and-versioning.md](features/data-entry-and-versioning.md).

### Review Pending Changes

If the table property `review_required=true` is set, submitted changes go to a review queue instead of publishing immediately.

Details are documented in [features/review-and-approval.md](features/review-and-approval.md).

## Local Development Notes

The app is designed to run inside Databricks Apps and uses the Databricks Apps `x-forwarded-access-token` header to connect as the signed-in user.

That means `streamlit run app.py` is not a complete local test path out of the box. You can still do code changes, static analysis, and non-runtime refactors locally, but functional verification requires running the app in Databricks Apps or mocking the Databricks-specific request context.

## Where To Go Next

- Runtime configuration: [configuration.md](configuration.md)
- Deployment commands: [deployment.md](deployment.md)
- Architecture and data model: [architecture.md](architecture.md)
- Common failures: [troubleshooting.md](troubleshooting.md)

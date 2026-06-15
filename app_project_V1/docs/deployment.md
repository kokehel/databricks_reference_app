# Deployment

This guide covers deployment to Databricks Apps for one or more customers.

## Prerequisites

- Databricks CLI installed in the deployment runner.
- A target workspace with Databricks Apps enabled.
- Permission to deploy apps in the target workspace.
- Permission to access the target catalog, schemas, and SQL warehouse.
- A configured Azure DevOps service connection for each Azure subscription.

## Deployment Model

The same application package is deployed everywhere. Runtime behavior is selected
by environment variables supplied by Databricks Apps or the Azure DevOps variable
group for the target customer/environment.

## Required Configuration

Every deployment needs:

```text
DATABRICKS_HOST
DATABRICKS_WAREHOUSE_ID
APP_NAME
APP_DISPLAY_NAME
APP_ENV
DEFAULT_SCHEMA
CATALOG_NAME or CATALOG_PREFIX
```

Optional:

```text
DEPLOY_SOURCE_PATH
APP_LOGO_PATH
```

## Manual Deployment

1. Export the required runtime values.
2. Run the deployment helper from the app source directory.

Example:

```bash
export DATABRICKS_HOST="https://example-workspace.azuredatabricks.net"
export DATABRICKS_WAREHOUSE_ID="warehouse-id"
export APP_NAME="customer-reference-data"
export APP_DISPLAY_NAME="Reference Data Manager"
export APP_ENV="dev"
export CATALOG_NAME="customer_reference_data_dev"
export DEFAULT_SCHEMA="default"

bash ../.azure/devops-pipelines/deploy_databricks_app.sh \
  "$APP_NAME" \
  "/Workspace/Users/me@databricks.com/databricks_apps/$APP_NAME" \
  true
```

The helper writes a deployment-specific `app.yaml` before syncing so the app
receives the same runtime values that were exported for deployment.

## Azure DevOps Deployment

The pipeline uses `.azure/devops-pipelines/templates/deploy-databricks-app-stage.yml`
for each environment. Put customer-specific values in variable groups such as:

```text
databricks-app-customer-a-dev
databricks-app-customer-a-uat
databricks-app-customer-a-prd
```

Each stage in `.azure/devops-pipelines/azure-pipelines.yml` references:

- an Azure service connection
- an Azure DevOps environment
- one variable group
- whether the app should be started before deployment

During deployment, `.azure/devops-pipelines/deploy_databricks_app.sh` generates
the runtime `app.yaml` from the variable group values before running
`databricks sync`.

## Verify Deployment

After deployment:

1. Open the app in Databricks Apps.
2. Confirm the sidebar shows the expected environment, catalog, and warehouse.
3. Confirm the expected schemas and tables are visible.
4. Confirm edits write to the expected catalog and schema.
5. If review is enabled for a table, confirm the Review & Approve tab appears.

## Useful CLI Commands

```bash
databricks apps list
databricks apps get "$APP_NAME"
databricks apps logs "$APP_NAME"
databricks apps stop "$APP_NAME"
databricks apps start "$APP_NAME"
databricks apps delete "$APP_NAME"
```

## Related Guides

- Getting started: [getting-started.md](getting-started.md)
- Runtime configuration: [configuration.md](configuration.md)
- Common failures: [troubleshooting.md](troubleshooting.md)

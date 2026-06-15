# Configuration

This app is configured explicitly by deployment environment variables. The source
code does not contain customer, subscription, workspace, or warehouse mappings.

## Required Runtime Values

| Variable | Required | Description |
| --- | --- | --- |
| `DATABRICKS_HOST` | yes | Target Databricks workspace host. |
| `DATABRICKS_WAREHOUSE_ID` | yes | SQL warehouse used by the signed-in user connection. |
| `APP_NAME` | yes | Databricks Apps application name. |
| `APP_DISPLAY_NAME` | recommended | UI title shown in the browser and sidebar. |
| `APP_ENV` | yes | Environment label such as `dev`, `uat`, or `prd`. |
| `DEFAULT_SCHEMA` | yes | Initial schema selected in the sidebar when available. |
| `CATALOG_NAME` | conditional | Exact Unity Catalog catalog to use. |
| `CATALOG_PREFIX` | conditional | Prefix used to build `{CATALOG_PREFIX}_{APP_ENV}` when `CATALOG_NAME` is not set. |
| `APP_LOGO_PATH` | no | Optional path to a customer-specific logo file. |

Set either `CATALOG_NAME` or `CATALOG_PREFIX`. Prefer `CATALOG_NAME` when a
customer does not follow the standard `{prefix}_{environment}` naming convention.

## Catalog Selection

Catalog selection happens in this order:

1. Use `CATALOG_NAME` when it is set.
2. Otherwise build the catalog as `{CATALOG_PREFIX}_{APP_ENV}`.
3. If `CATALOG_PREFIX` is not set, derive it from `APP_NAME` by replacing hyphens with underscores.

Example:

```text
APP_NAME=reference-data-app
APP_ENV=prd
CATALOG_PREFIX=customer_reference_data
```

resolves to:

```text
customer_reference_data_prd
```

## Warehouse Selection

`DATABRICKS_WAREHOUSE_ID` is required. The app no longer infers warehouses from
workspace IDs and no longer falls back to a development warehouse. This avoids
accidental cross-customer or cross-environment deployments.

## `app.yaml`

The source `app.yaml` contains neutral defaults only. The CI/CD deployment
helper writes a deployment-specific `app.yaml` before syncing the app source so
customer-specific values are present at runtime.

## Azure DevOps

Store customer/environment values in variable groups. A typical set is:

```text
databricks-app-customer-a-dev
databricks-app-customer-a-uat
databricks-app-customer-a-prd
```

Each variable group should define the required runtime values above. Service
connections stay in the pipeline stage parameters because Azure DevOps resolves
them separately from runtime variables.

## Related Guides

- Deployment steps: [deployment.md](deployment.md)
- Table-level behavior flags: [reference/table-properties.md](reference/table-properties.md)
- Failure scenarios: [troubleshooting.md](troubleshooting.md)

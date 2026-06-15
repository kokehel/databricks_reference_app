#!/usr/bin/env bash

set -euo pipefail

APP_NAME="${1:?Usage: deploy_databricks_app.sh <app_name> <source_path> <start_if_needed>}"
APP_SOURCE_PATH="${2:?Usage: deploy_databricks_app.sh <app_name> <source_path> <start_if_needed>}"
START_IF_NEEDED="${3:?Usage: deploy_databricks_app.sh <app_name> <source_path> <start_if_needed>}"

if [[ -z "${DATABRICKS_HOST:-}" ]]; then
  echo "DATABRICKS_HOST must be set before calling deploy_databricks_app.sh." >&2
  exit 1
fi

if [[ -z "${DATABRICKS_WAREHOUSE_ID:-}" ]]; then
  echo "DATABRICKS_WAREHOUSE_ID must be set for a generic deployment." >&2
  exit 1
fi

yaml_quote() {
  local value="$1"
  value="${value//\'/\'\'}"
  printf "'%s'" "$value"
}

write_app_yaml() {
  local app_display_name="${APP_DISPLAY_NAME:-Reference Data Manager}"
  local app_env="${APP_ENV:-dev}"
  local default_schema="${DEFAULT_SCHEMA:-default}"
  local catalog_prefix="${CATALOG_PREFIX:-}"
  local catalog_name="${CATALOG_NAME:-}"
  local app_logo_path="${APP_LOGO_PATH:-}"

  echo "Writing deployment-specific app.yaml"
  {
    echo "command:"
    echo "  - streamlit"
    echo "  - run"
    echo "  - app.py"
    echo ""
    echo "env:"
    echo "  - name: STREAMLIT_BROWSER_GATHER_USAGE_STATS"
    echo "    value: \"false\""
    echo "  - name: STREAMLIT_SERVER_HEADLESS"
    echo "    value: \"true\""
    echo "  - name: APP_NAME"
    echo "    value: $(yaml_quote "$APP_NAME")"
    echo "  - name: APP_DISPLAY_NAME"
    echo "    value: $(yaml_quote "$app_display_name")"
    echo "  - name: APP_ENV"
    echo "    value: $(yaml_quote "$app_env")"
    echo "  - name: DEFAULT_SCHEMA"
    echo "    value: $(yaml_quote "$default_schema")"
    echo "  - name: DATABRICKS_WAREHOUSE_ID"
    echo "    value: $(yaml_quote "$DATABRICKS_WAREHOUSE_ID")"
    if [[ -n "$catalog_name" ]]; then
      echo "  - name: CATALOG_NAME"
      echo "    value: $(yaml_quote "$catalog_name")"
    elif [[ -n "$catalog_prefix" ]]; then
      echo "  - name: CATALOG_PREFIX"
      echo "    value: $(yaml_quote "$catalog_prefix")"
    fi
    if [[ -n "$app_logo_path" ]]; then
      echo "  - name: APP_LOGO_PATH"
      echo "    value: $(yaml_quote "$app_logo_path")"
    fi
  } > app.yaml
}

echo "Deployment configuration:"
echo "  App name: $APP_NAME"
echo "  Source path: $APP_SOURCE_PATH"
echo "  Databricks host: $DATABRICKS_HOST"
echo "  App environment: ${APP_ENV:-unset}"
echo "  Catalog name: ${CATALOG_NAME:-unset}"
echo "  Catalog prefix: ${CATALOG_PREFIX:-unset}"
echo "  Default schema: ${DEFAULT_SCHEMA:-unset}"

write_app_yaml

get_app_field() {
  local field_name="$1"
  case "$field_name" in
    compute_state)
      databricks apps get "$APP_NAME" -o json | jq -r '.compute_status.state // ""'
      ;;
    pending_state)
      databricks apps get "$APP_NAME" -o json | jq -r '.pending_deployment.status.state // ""'
      ;;
    *)
      echo "Unsupported field: $field_name" >&2
      return 1
      ;;
  esac
}

wait_for_no_pending_deployment() {
  local max_attempts=40
  local attempt=1
  local pending_state=""

  while [[ "$attempt" -le "$max_attempts" ]]; do
    pending_state="$(get_app_field pending_state)"
    if [[ -z "$pending_state" ]]; then
      echo "No pending deployment in progress."
      return 0
    fi

    echo "Pending deployment state: $pending_state"
    if [[ "$pending_state" != "IN_PROGRESS" ]]; then
      echo "Pending deployment is no longer in progress."
      return 0
    fi

    echo "Waiting 30 seconds for pending deployment to finish..."
    sleep 30
    attempt=$((attempt + 1))
  done

  echo "Timed out waiting for pending deployment to finish." >&2
  return 1
}

echo "Syncing app source code to $APP_SOURCE_PATH"
databricks sync . "$APP_SOURCE_PATH"

case "$START_IF_NEEDED" in
  true)
    compute_state="$(get_app_field compute_state)"
    if [[ "$compute_state" != "ACTIVE" ]]; then
      echo "App compute is '$compute_state'. Starting app..."
      databricks apps start "$APP_NAME"
    else
      echo "App compute is already ACTIVE. Skipping start."
    fi
    ;;
  false)
    echo "Start-if-needed disabled. Skipping app start."
    ;;
  *)
    echo "Invalid start_if_needed value: $START_IF_NEEDED. Use true or false." >&2
    exit 1
    ;;
esac

wait_for_no_pending_deployment

echo "Deploying app '$APP_NAME' from $APP_SOURCE_PATH"
databricks apps deploy "$APP_NAME" --source-code-path "$APP_SOURCE_PATH"

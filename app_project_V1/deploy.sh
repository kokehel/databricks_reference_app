#!/usr/bin/env bash
# Local helper for validating customer-neutral deployment configuration.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--dir)
            APP_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -d, --dir DIR    Set app directory [default: $APP_DIR]"
            echo "  -h, --help       Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "App directory: $APP_DIR"

if [[ ! -f "$APP_DIR/app.py" ]]; then
    echo "Error: app.py not found in $APP_DIR"
    exit 1
fi

if [[ ! -f "$APP_DIR/app.yaml" ]]; then
    echo "Error: app.yaml not found in $APP_DIR"
    exit 1
fi

echo "Required runtime configuration:"
echo "  APP_NAME=${APP_NAME:-<set per deployment>}"
echo "  APP_DISPLAY_NAME=${APP_DISPLAY_NAME:-<set per deployment>}"
echo "  APP_ENV=${APP_ENV:-<set per deployment>}"
echo "  CATALOG_NAME=${CATALOG_NAME:-<optional when CATALOG_PREFIX is set>}"
echo "  CATALOG_PREFIX=${CATALOG_PREFIX:-<optional when CATALOG_NAME is set>}"
echo "  DEFAULT_SCHEMA=${DEFAULT_SCHEMA:-<set per deployment>}"
echo "  DATABRICKS_HOST=${DATABRICKS_HOST:-<set per deployment>}"
echo "  DATABRICKS_WAREHOUSE_ID=${DATABRICKS_WAREHOUSE_ID:-<set per deployment>}"
echo ""
echo "Deployment preparation complete. Use Databricks Apps or Azure DevOps variable groups to provide these values."

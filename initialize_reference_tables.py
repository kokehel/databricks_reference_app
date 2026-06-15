# Databricks notebook source

# MAGIC %md
# MAGIC # Initialize Reference Tables
# MAGIC
# MAGIC This notebook handles the creation and recreation of reference data tables based on metadata
# MAGIC from CSV files. It provides functionality to create empty tables with proper schemas,
# MAGIC handle table recreation with data backup, and manage table properties.
# MAGIC
# MAGIC ## Key Features
# MAGIC
# MAGIC - **Metadata-driven table creation** from CSV files
# MAGIC - **Automatic schema generation** based on column types
# MAGIC - **Table recreation with data backup** capabilities
# MAGIC - **Business key detection** and table property management
# MAGIC - **Comprehensive error handling** and logging
# MAGIC
# MAGIC **Author:** Thijs Kuipers
# MAGIC **Last Updated:** 2025-09-30

# COMMAND ----------

# Clear Spark cache for fresh execution
spark.catalog.clearCache()

# COMMAND ----------

# MAGIC %run ./initial_table_setup

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration
# MAGIC
# MAGIC The following configuration is used for table creation and recreation:

# COMMAND ----------
import os
import textwrap

from pyspark.sql.types import StructType

# Get parameters from Databricks job widgets
dbutils.widgets.text("target_schema", "l2f", "Target Schema Name")

# Get environment from Spark configuration
environment = os.getenv("ENVIRONMENT")
spark.conf.set("env", environment)
env = spark.conf.get("env")

# Target catalog and schema configuration
TARGET_CATALOG: str = f"referencedataapp_{env}"
TARGET_SCHEMA: str = dbutils.widgets.get("target_schema")
BASE_META_PATH: str = f"dbfs:/Volumes/referencedataapp_{env}/{TARGET_SCHEMA}/{TARGET_SCHEMA}/schemas/{TARGET_SCHEMA}_reference_tables_meta_data*.csv"
BASE_TABLE_CONFIG_PATH: str = f"dbfs:/Volumes/referencedataapp_{env}/{TARGET_SCHEMA}/{TARGET_SCHEMA}/table_config/{TARGET_SCHEMA}_reference_tables_table_config*.csv"

TABLES_TO_RECREATE: list[str] = []

# Tables to exclude (specify table names from metadata Tabelnaam column)
# Use this to limit which tables are created, e.g. to create a single table
# provide all others here (or leave only the desired table out)
TABLES_TO_EXCLUDE: list[str] = [
    # "deliverystatus",
]

print(f"Environment: {env}")
print(f"Target Catalog: {TARGET_CATALOG}")
print(f"Target Schema: {TARGET_SCHEMA}")
print(f"Base Metadata Path: {BASE_META_PATH}")
print(f"Base Table Config Path: {BASE_TABLE_CONFIG_PATH}")
print(f"Tables to Exclude: {TABLES_TO_EXCLUDE or 'None'}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Metadata File Discovery and Schema Building

# COMMAND ----------

def log_reinit_details(
    *,
    full_table_name: str,
    desired_schema: StructType,
    current_props: dict[str, str],
    desired_col_fingerprint: str,
    desired_cfg_fingerprint: str,
    table_name: str,
    table_config_df,
) -> None:
    # Extract table name from full_table_name for display (format: catalog.schema.table)
    display_table_name = full_table_name.split('.')[-1]

    old_col_fp = current_props.get("column_metadata_fingerprint")
    old_cfg_fp = current_props.get("table_config_fingerprint")

    if old_col_fp != desired_col_fingerprint:
        print(
            f"[CHANGE] {display_table_name}: column_metadata_fingerprint: {old_col_fp or '<missing>'} -> {desired_col_fingerprint}"
        )
    if old_cfg_fp != desired_cfg_fingerprint:
        print(
            f"[CHANGE] {display_table_name}: table_config_fingerprint: {old_cfg_fp or '<missing>'} -> {desired_cfg_fingerprint}"
        )

    # Schema diff (ignore metadata columns starting with '__')
    current_schema = spark.table(full_table_name).schema
    current_user_fields = {
        f.name: f for f in current_schema.fields if not f.name.startswith("__")
    }
    desired_user_fields = {f.name: f for f in desired_schema.fields}

    added_cols = sorted(desired_user_fields.keys() - current_user_fields.keys())
    removed_cols = sorted(current_user_fields.keys() - desired_user_fields.keys())
    changed_cols: list[str] = []
    for col_name in sorted(current_user_fields.keys() & desired_user_fields.keys()):
        old_f = current_user_fields[col_name]
        new_f = desired_user_fields[col_name]
        if old_f.dataType != new_f.dataType or old_f.nullable != new_f.nullable:
            changed_cols.append(
                f"{col_name}: {old_f.dataType.simpleString()}{' NULL' if old_f.nullable else ' NOT NULL'}"
                f" -> {new_f.dataType.simpleString()}{' NULL' if new_f.nullable else ' NOT NULL'}"
            )

    if added_cols:
        print(f"[SCHEMA] Added: {', '.join(added_cols)}")
    if removed_cols:
        print(f"[SCHEMA] Removed: {', '.join(removed_cols)}")
    if changed_cols:
        print("[SCHEMA] Changed:")
        for line in changed_cols:
            print(f"  - {line}")

    # Table-config diff for key settings (if present as table properties)
    cfg_row = (
        table_config_df.filter(table_config_df["Tabelnaam"] == table_name)
        .limit(1)
        .collect()[0]
    )
    desired_bulk = str(cfg_row["bulk_insert"]).strip()
    desired_single = str(cfg_row["single_insert"]).strip()

    old_bulk = current_props.get("bulk_insert")
    old_single = current_props.get("single_insert")
    if old_bulk != desired_bulk:
        print(f"[CONFIG] bulk_insert: {old_bulk or '<missing>'} -> {desired_bulk}")
    if old_single != desired_single:
        print(f"[CONFIG] single_insert: {old_single or '<missing>'} -> {desired_single}")

# COMMAND ----------

# Read table-level config
TABLE_CONFIG_PATH: str = find_latest_metadata_file(
    base_path=BASE_TABLE_CONFIG_PATH,
    file_pattern=f"{TARGET_SCHEMA}_reference_tables_table_config",
)
table_config_df = (
    spark.read.option("header", "true").option("sep", ";").csv(TABLE_CONFIG_PATH)
)
print(f"Table config file loaded: {TABLE_CONFIG_PATH}")

# COMMAND ----------

# Find the latest metadata file
META_PATH: str = find_latest_metadata_file(
    base_path=BASE_META_PATH,
    file_pattern=f"{TARGET_SCHEMA}_reference_tables_meta_data",
)

# Read the selected metadata file
meta_df = spark.read.option("header", "true").option("sep", ";").csv(META_PATH)

# COMMAND ----------

# Cache all schemas once - get unique table names from metadata
unique_table_names: list[str] = [
    row["Tabelnaam"] for row in meta_df.select("Tabelnaam").distinct().collect()
]
SCHEMAS: dict[str, StructType] = {
    table_name: build_schema_for_table(table_name, meta_df)
    for table_name in unique_table_names
}

# Apply exclusions to determine actual target tables for processing
target_table_names: list[str] = [
    t for t in unique_table_names if t not in TABLES_TO_EXCLUDE
]

print(f"Metadata file loaded: {META_PATH}")
print(f"Total metadata rows: {meta_df.count()}")
print(f"for {len(SCHEMAS)} different tables")

# COMMAND ----------

# Get already existing tables to skip creation
existing_tables: set = {
    row.tableName
    for row in spark.sql(
        f"SHOW TABLES IN {TARGET_CATALOG}.{TARGET_SCHEMA}"
    ).collect()
    if "_current" not in row.tableName and "_sqldf" not in row.tableName
}

print(
    textwrap.dedent(f"""
    Creating empty tables based on metadata...
    ────────────────────────────────────────────────────────────
    Found {len(unique_table_names)} unique table names in metadata file: {unique_table_names}
    After exclusions, {len(target_table_names)} target table(s): {target_table_names}
    Found {len(existing_tables)} existing tables in target schema: {existing_tables}
    ────────────────────────────────────────────────────────────""").strip()
)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Main Table Creation Logic

# COMMAND ----------

# Track tables that failed to update (for summary reporting)
failed_updates: list[str] = []
critical_failures: list[str] = []

for table_name in target_table_names:
    # Clean the table name to ensure it's properly formatted
    clean_table: str = clean_table_name(table_name)
    full_table_name: str = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{clean_table}"
    schema: StructType = SCHEMAS[table_name]

    table_exists = clean_table in existing_tables
    if table_exists:
        current_props = get_tblproperties(full_table_name)
        desired_col_fingerprint = compute_column_metadata_fingerprint(table_name, meta_df)
        desired_cfg_fingerprint = compute_table_config_fingerprint(table_name, table_config_df)

        needs_reinit = (
            current_props.get("column_metadata_fingerprint") != desired_col_fingerprint
            or current_props.get("table_config_fingerprint") != desired_cfg_fingerprint
        )

        if not needs_reinit:
            print(f"[SKIP] {clean_table} unchanged")
            continue

        log_reinit_details(
            full_table_name=full_table_name,
            desired_schema=schema,
            current_props=current_props,
            desired_col_fingerprint=desired_col_fingerprint,
            desired_cfg_fingerprint=desired_cfg_fingerprint,
            table_name=table_name,
            table_config_df=table_config_df,
        )

        print(f"[REINIT] {clean_table} changed - backing up, recreating, restoring")

        backup_table_name = backup_and_recreate_table(full_table_name, schema)
        if not backup_table_name:
            print(f"[ERROR] Failed to recreate {clean_table}")
            continue

        # Attempt to restore data from backup with error handling
        try:
            restore_data_from_backup(full_table_name, backup_table_name)
            add_table_properties(full_table_name, table_name, meta_df, table_config_df)
            spark.sql(f"DROP TABLE {backup_table_name}")
            print(f"  → Backup table dropped")
            print(f"[✓] Reinitialized table: {clean_table}")
        except Exception as restore_error:
            error_msg = str(restore_error).split('\n')[0]  # Get first line only
            print(f"[ERROR] Failed to restore data from backup: {error_msg}")
            print(f"[ROLLBACK] Restoring original table from backup...")

            # Restore the original table from backup
            try:
                restore_original_table_from_backup(full_table_name, backup_table_name)
                # Clean up backup table after successful rollback
                spark.sql(f"DROP TABLE {backup_table_name}")
                print(f"  → Backup table dropped")
                print(f"[✓] Original table restored successfully")
                print(f"[WARNING] Table {clean_table} was not updated due to metadata errors. Please fix metadata and retry.")
                failed_updates.append(clean_table)
            except Exception as rollback_error:
                error_msg = str(rollback_error).split('\n')[0]  # Get first line only
                print(f"[CRITICAL] Failed to restore original table: {error_msg}")
                print(f"[WARNING] Backup table {backup_table_name} is preserved for manual recovery")
                # Don't drop backup if rollback fails - it's the only copy of the data
                critical_failures.append(clean_table)
                raise
        continue

    print(
        textwrap.dedent(f"""
        ────────────────────────────────────────────────────────────
        Creating: {clean_table}
        Target  : {full_table_name}
        Schema  : {len(schema.fields)} columns
        ────────────────────────────────────────────────────────────""").strip()
    )

    # Create the table using the reusable function
    create_empty_table_with_metadata(full_table_name, schema, "schema_only")

    # Add table properties
    add_table_properties(full_table_name, table_name, meta_df, table_config_df)

    print(f"[✓] Created empty table: {clean_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

print("\n[✔] All tables created based on metadata.")
print(f"Total tables processed: {len(target_table_names)}")
print(
    f"New tables created: {len([t for t in target_table_names if clean_table_name(t) not in existing_tables])}"
)
print("Note: existing tables are skipped unless metadata/config fingerprint changed.")

# Report any problems encountered during table updates
if failed_updates:
    print(f"Tables rolled back due to metadata errors: {', '.join(failed_updates)}")

if critical_failures:
    print(f"Critical failures (backup preserved): {', '.join(critical_failures)}")

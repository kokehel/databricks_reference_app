# Databricks notebook source

# MAGIC %md
# MAGIC # Initial Table Setup Module
# MAGIC
# MAGIC This module provides functions for creating and recreating reference data tables based on metadata
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

# Standard library imports
import hashlib
import json
import pathlib
import re
from datetime import datetime

from pyspark.sql import DataFrame
from pyspark.sql import functions as f

# PySpark imports
from pyspark.sql.types import (
    BooleanType,
    DateType,
    DoubleType,
    FloatType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
    DecimalType
)

# ────────────────────────────────────────────────────────────────────────────────
# Main Functions
# ────────────────────────────────────────────────────────────────────────────────


def find_latest_metadata_file(base_path: str, file_pattern: str) -> str:
    """
    Find the metadata file with the latest date in the filename.

    This function searches for metadata files matching the pattern and selects
    the one with the most recent date in the filename.

    Args:
        base_path: Base path pattern for metadata files
        file_pattern: Pattern to match in filename (e.g., "reference_tables_meta_data" or "table_config")
    Returns:
        str: Path to the latest metadata file

    Raises:
        FileNotFoundError: If no valid metadata files are found
    """
    # Extract the directory path and filename pattern
    if base_path.startswith("dbfs:"):
        # For DBFS paths, we need to use dbutils
        try:
            # List files matching the pattern
            files = dbutils.fs.ls(base_path.replace("*.csv", ""))
            matching_files: list[str] = [
                f.path
                for f in files
                if f.name.startswith(file_pattern)
                and f.name.endswith(".csv")
            ]
        except Exception:
            # Fallback: try to read with wildcard and get the file paths
            temp_df = spark.read.csv(base_path)
            # Get the file paths from the DataFrame
            files = temp_df.inputFiles()
            matching_files = [
                f
                for f in files
                if file_pattern in f and f.endswith(".csv")
            ]
    else:
        # For local paths
        directory = pathlib.Path(base_path).parent
        pathlib.Path(base_path).name.replace("*", "")
        matching_files = [
            str(directory / f)
            for f in directory.iterdir()
            if f.name.startswith(file_pattern)
            and f.name.endswith(".csv")
        ]

    if not matching_files:
        error_msg = f"No metadata files found matching pattern: {base_path}"
        raise FileNotFoundError(error_msg)

    # Extract dates from filenames and find the latest
    latest_file: str | None = None
    latest_date: datetime | None = None

    for file_path in matching_files:
        filename = pathlib.Path(file_path).name
        # Extract date from filename using file_pattern: {file_pattern}_YYYYMMDD.csv
        match = re.search(rf"{re.escape(file_pattern)}_(\d{{8}})\.csv", filename)
        if match:
            date_str = match.group(1)
            try:
                file_date = datetime.strptime(date_str, "%Y%m%d")
                if latest_date is None or file_date > latest_date:
                    latest_date = file_date
                    latest_file = file_path
            except ValueError:
                # Skip files with invalid date format
                continue

    if latest_file is None:
        error_msg = f"No valid metadata files with date found. Available files: {matching_files}"
        raise FileNotFoundError(error_msg)

    print(
        f"Selected metadata file: {pathlib.Path(latest_file).name} (date: {latest_date.strftime('%Y-%m-%d')})"
    )
    return latest_file


# ────────────────────────────────────────────────────────────────────────────────
# Type Mapping and Schema Generation
# ────────────────────────────────────────────────────────────────────────────────

_TYPE_LOOKUP = {
    "STRING": StringType(),
    "VARCHAR": StringType(),
    "CHAR": StringType(),
    "INTEGER": IntegerType(),
    "INT": IntegerType(),
    "BIGINT": LongType(),
    "LONG": LongType(),
    "FLOAT": FloatType(),
    "DOUBLE": DoubleType(),
    "DECIMAL": DecimalType(precision=38, scale=2),
    "BOOLEAN": BooleanType(),
    "DATE": DateType(),
    "DATETIME": TimestampType(),
    "TIMESTAMP": TimestampType(),
}


def _to_spark_type(type_txt: str) -> object:
    """
    Convert a generic SQL type string to a Spark DataType.

    Args:
        type_txt: Type string from metadata

    Returns:
        Spark DataType object, defaults to StringType if unknown
    """
    cleaned_type = type_txt.strip().upper()
    return _TYPE_LOOKUP.get(cleaned_type, StringType())


# ────────────────────────────────────────────────────────────────────────────────
# Data Normalization Helpers
# ────────────────────────────────────────────────────────────────────────────────


def _norm(col_name: str) -> str:
    """
    Normalize column names by trimming whitespace and replacing multiple spaces with underscores.

    Args:
        col_name: Original column name

    Returns:
        str: Normalized column name in lowercase
    """
    return re.sub(r"\s+", "_", col_name.strip()).lower()


def clean_table_name(filename: str) -> str:
    """
    Convert arbitrary table name to safe table name (snake-case, no dates).

    This function removes dates, special characters, and normalizes the table name
    to ensure it's safe for database operations.

    Args:
        filename: Original filename or table name

    Returns:
        str: Clean, normalized table name
    """
    name = filename[:-4] if filename.lower().endswith(".csv") else filename

    # Remove dates like 31-07-2025 or 20250731
    name = re.sub(r"(?i)(?:\b\d{1,2}[-_]\d{1,2}[-_]\d{2,4}\b)", "", name)
    name = re.sub(r"\b(?:19|20)\d{2}\b", "", name)
    name = re.sub(r"\b\d{8,}\b", "", name)  # 8+ digit blobs
    name = re.sub(r"[-_\s]+$", "", name)  # trailing separators
    name = re.sub(r"^[-_\s]+", "", name)  # leading separators
    name = re.sub(r"[-\s]+", "_", name)  # inside separators → _
    name = re.sub(r"__+", "_", name)  # collapse double underscores
    name = name.strip("_").lower()

    # Ensure name doesn't start with digit
    if not name or name[0].isdigit():
        name = f"_{name}"

    return name


# ────────────────────────────────────────────────────────────────────────────────
# Schema Building and Business Key Detection
# ────────────────────────────────────────────────────────────────────────────────


def build_schema_for_table(table_name: str, meta_df: DataFrame) -> StructType:
    """
    Build a Spark StructType schema for a table based on metadata.

    Args:
        table_name: Name of the table to build schema for
        meta_df: Metadata DataFrame containing table schema information

    Returns:
        StructType: Spark schema for the table

    Raises:
        ValueError: If no metadata rows found for the table
    """
    rows = (
        meta_df.filter(f.col("Tabelnaam") == table_name)
        .select("Veldnaam", "Type", "nullable")
        .collect()
    )

    if not rows:
        error_msg = f"No rows found for Tabelnaam='{table_name}'"
        raise ValueError(error_msg)

    # Preserve metadata order as given in the CSV, but we'll *cast* later so the
    # on-disk order stays aligned to the raw csv columns.
    fields = [
        StructField(
            name=_norm(r["Veldnaam"]),
            dataType=_to_spark_type(r["Type"]),
            nullable=r["nullable"].lower() == "true",
        )
        for r in rows
    ]

    return StructType(fields)


def get_business_keys_for_table(
    table_name: str, meta_df: DataFrame
) -> dict[str, list[str]]:
    """
    Extract business keys from metadata, handling both single and composite keys.

    Args:
        table_name: Name of the table to extract keys for
        meta_df: Metadata DataFrame containing business key information

    Returns:
        Dict containing single_keys and/or composite_key groups
    """
    rows = (
        meta_df.filter(f.col("Tabelnaam") == table_name)
        .select("Veldnaam", "Uniek", "Composite_Key")
        .collect()
    )

    # Group columns by their unique key identifier
    key_groups: dict[str, list[str]] = {}
    single_keys: list[str] = []

    for row in rows:
        uniek_value: str = str(row["Uniek"]).strip().lower()
        composite_key_value: str = str(row["Composite_Key"]).strip().upper()
        column_name: str = _norm(row["Veldnaam"])

        if uniek_value == "true":
            # Single column primary key
            single_keys.append(column_name)
        elif composite_key_value and composite_key_value != "NONE":
            # Composite key - group by the key identifier
            key_id = composite_key_value
            if key_id not in key_groups:
                key_groups[key_id] = []
            key_groups[key_id].append(column_name)

    # Combine single keys and composite keys
    result: dict[str, list[str]] = {}
    if single_keys:
        result["single_keys"] = single_keys

    for key_id, columns in key_groups.items():
        result[f"composite_key_{key_id}"] = columns

    return result


# ────────────────────────────────────────────────────────────────────────────────
# Table Creation
# ────────────────────────────────────────────────────────────────────────────────


def create_empty_table_with_metadata(
    full_table_name: str, schema: StructType, upload_type: str = "schema_only"
) -> None:
    """
    Create an empty table with the specified schema and standard metadata columns.

    Args:
        full_table_name: Full table name (catalog.schema.table)
        schema: Schema for the table
        upload_type: Type of upload (e.g., "schema_only", "recreated")
    """
    # Create empty DataFrame with the schema
    empty_df = spark.createDataFrame([], schema)

    # Add surrogate key column (starts at 1)
    empty_df = empty_df.withColumn("__KEY", f.lit(1).cast("bigint"))

    # Re-order columns to put __KEY first
    original_cols = empty_df.columns
    original_cols.remove("__KEY")
    ordered_cols = ["__KEY", *original_cols]
    empty_df = empty_df.select(*ordered_cols)

    # Add metadata columns
    upload_file_name = (
        "metadata_created"
        if upload_type == "schema_only"
        else "metadata_recreated"
    )
    empty_df = (
        empty_df.withColumn("__UPLOAD_TIMESTAMP", f.current_timestamp())
        .withColumn("__VERSION", f.lit(1))
        .withColumn("__VERSION_TIMESTAMP", f.current_timestamp())
        .withColumn("__UPLOADED_BY", f.current_user())
        .withColumn("__UPLOAD_FILE_NAME", f.lit(upload_file_name))
    )

    # Create the table
    (empty_df.write.mode("overwrite").saveAsTable(full_table_name))


# ────────────────────────────────────────────────────────────────────────────────
# Table Backup and Recreation
# ────────────────────────────────────────────────────────────────────────────────


def backup_and_recreate_table(full_table_name: str, schema: StructType) -> str | None:
    """
    Backup existing data and recreate table with new schema.

    This function creates a backup of the existing table using SHALLOW CLONE,
    drops the original table, and creates a new table with the updated schema.

    Args:
        full_table_name: Full table name (catalog.schema.table)
        schema: New schema for the table

    Returns:
        Backup table name if successful, None otherwise
    """
    try:
        print("  → Backing up existing data and recreating table...")

        # Step 1: Create backup using SHALLOW CLONE (preserves properties and is faster)
        timestamp: int = int(datetime.now().timestamp())
        backup_table_name: str = f"{full_table_name}_backup_{timestamp}"

        # Create backup table using SHALLOW CLONE
        print(f"  → Creating backup table: {backup_table_name}")
        spark.sql(
            f"CREATE TABLE {backup_table_name} SHALLOW CLONE {full_table_name}"
        )
        print(
            f"  → Data backed up to: {backup_table_name} with original schema and properties"
        )

        # Step 2: Drop the original table
        spark.sql(f"DROP TABLE {full_table_name}")
        print("  → Original table dropped")

        # Step 3: Create new table with updated schema
        print(f"  → Creating table with schema: {schema}")
        create_empty_table_with_metadata(full_table_name, schema, "recreated")
        print("  → New table created with updated schema")
        print(f"  → Data is available in backup table: {backup_table_name}")

    except Exception as e:
        print(f"  → Error during table recreation: {e!s}")
        return None
    else:
        return backup_table_name


def restore_data_from_backup(
    full_table_name: str, backup_table_name: str
) -> None:
    """
    Restore data from a backup table into the (re)created target table.

    Columns are aligned by name:
    - Columns present in both tables are copied over
    - Columns missing in the backup are filled with NULL
    - Columns present only in the backup are ignored

    Raises:
        Exception: If the restore operation fails (e.g., due to incompatible data types)
    """
    target_cols: list[str] = spark.table(full_table_name).columns
    backup_cols: set[str] = set(spark.table(backup_table_name).columns)

    select_exprs: list[str] = []
    for col_name in target_cols:
        if col_name in backup_cols:
            select_exprs.append(f"`{col_name}`")
        else:
            select_exprs.append(f"NULL AS `{col_name}`")

    cols_sql = ", ".join([f"`{c}`" for c in target_cols])
    select_sql = ", ".join(select_exprs)

    spark.sql(
        f"INSERT INTO {full_table_name} ({cols_sql}) SELECT {select_sql} FROM {backup_table_name}"
    )


def restore_original_table_from_backup(
    full_table_name: str, backup_table_name: str
) -> None:
    """
    Restore the original table from a backup table using CREATE TABLE AS SELECT.

    This function is used to rollback when table recreation fails.
    It drops the failed table and recreates it from the backup by copying all data.
    Uses CREATE TABLE AS SELECT instead of CLONE because the backup is already
    a SHALLOW CLONE and cannot be cloned again.

    Args:
        full_table_name: Full table name (catalog.schema.table) to restore
        backup_table_name: Backup table name to restore from
    """
    print(f"  → Restoring original table from backup: {backup_table_name}")

    # Drop the failed table
    spark.sql(f"DROP TABLE IF EXISTS {full_table_name}")
    print("  → Dropped failed table")

    # Restore from backup using CREATE TABLE AS SELECT
    # This avoids the "cannot shallow clone a shallow clone" error
    spark.sql(f"CREATE TABLE {full_table_name} AS SELECT * FROM {backup_table_name}")
    print(f"  → Original table restored from backup")


def get_tblproperties(full_table_name: str) -> dict[str, str]:
    """Return table properties as a dict (empty if none)."""
    rows = spark.sql(f"SHOW TBLPROPERTIES {full_table_name}").collect()
    return {r.key: r.value for r in rows}


def _compute_fingerprint_from_rows(rows: list[dict]) -> str:
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_column_metadata_fingerprint(table_name: str, meta_df: DataFrame) -> str:
    cols = [
        "Tabelnaam",
        "Veldnaam",
        "Type",
        "nullable",
        "not_editable",
        "Uniek",
        "Composite_Key",
        "valid_from",
        "valid_to",
        "validity_key",
    ]
    rows = (
        meta_df.filter(f.col("Tabelnaam") == table_name)
        .select(*[c for c in cols if c in meta_df.columns])
        .orderBy(f.col("Veldnaam"))
        .collect()
    )
    return _compute_fingerprint_from_rows([r.asDict(recursive=True) for r in rows])


def compute_table_config_fingerprint(table_name: str, table_config_df: DataFrame) -> str:
    # For table-level config we expect one row per table; still hash deterministically.
    cols = [c for c in table_config_df.columns if c != "Tabelnaam"]
    rows = (
        table_config_df.filter(f.col("Tabelnaam") == table_name)
        .select(*cols)
        .orderBy(*cols)
        .collect()
    )
    return _compute_fingerprint_from_rows([r.asDict(recursive=True) for r in rows])


def add_table_properties(
    full_table_name: str,
    table_name: str,
    meta_df: DataFrame,
    table_config_df: DataFrame,
) -> None:
    """
    Add table properties for business keys and schema information.

    This function sets table properties including business key information,
    nullable column details, and metadata about the table creation.

    Args:
        full_table_name: Full table name (catalog.schema.table)
        table_name: Original table name for business key lookup
        meta_df: Metadata DataFrame for business key lookup
    """
    # Initialize base properties
    properties: dict[str, str] = {
        "table_type": "reference_data",
        "created_by": "metadata_initial_table_setup",
    }

    # Get table metadata rows once
    table_rows = meta_df.filter(f.col("Tabelnaam") == table_name).collect()

    # Table-level configuration rows
    table_config_rows = (
        table_config_df.filter(f.col("Tabelnaam") == table_name).collect()
    )

    # Process business keys
    business_keys = get_business_keys_for_table(table_name, meta_df)
    if business_keys:
        _process_business_keys(properties, business_keys)

    # Process nullable columns from metadata
    nullable_columns, not_null_columns = _process_columns_from_metadata(
        table_rows,
        "nullable",
        properties,
        "nullable_columns",
        "not_null_columns",
    )

    # Process not editable columns from metadata
    not_editable_columns, _editable_columns = _process_columns_from_metadata(
        table_rows, "not_editable", properties, "not_editable"
    )

    # Process valid_from/valid_to/validity_key properties
    valid_from_column = _process_columns_from_metadata(table_rows, "valid_from", properties, "valid_from")
    valid_to_column = _process_columns_from_metadata(table_rows, "valid_to", properties, "valid_to")
    validity_key = _process_columns_from_metadata(table_rows, "validity_key", properties, "validity_key")

    # Process insert operation properties
    _add_metadata_property_value(properties, table_config_rows, "bulk_insert")
    _add_metadata_property_value(properties, table_config_rows, "single_insert")
    _add_metadata_property_value(properties, table_config_rows, "review_required")

    # Fingerprints for change detection
    properties["column_metadata_fingerprint"] = compute_column_metadata_fingerprint(
        table_name, meta_df
    )
    properties["table_config_fingerprint"] = compute_table_config_fingerprint(
        table_name, table_config_df
    )

    # Set table properties
    for key, value in properties.items():
        spark.sql(
            f"ALTER TABLE {full_table_name} SET TBLPROPERTIES ('{key}' = '{value}')"
        )

    print(
        f"  → Nullable columns: {len(nullable_columns)}, Not-null columns: {len(not_null_columns)}"
    )
    if not_editable_columns:
        print(f"  → Not editable columns: {', '.join(not_editable_columns)}")

    if valid_from_column:
        print(f"  → Valid from column: {valid_from_column}")
    if valid_to_column:
        print(f"  → Valid to column: {valid_to_column}")
    if validity_key:
        print(f"  → Validity key: {validity_key}")



def _process_columns_from_metadata(
    table_rows: list,
    metadata_column: str,
    properties: dict[str, str],
    property_key: str,
    non_matching_property_key: str | None = None,
) -> tuple[list[str], list[str]]:
    """Process columns based on metadata column values and add to properties. This functions checks
    for the values true and false. If true, the column name is added to the matching_columns list, if false, the column name
    is added to the non_matching_columns list."""

    matching_columns: list[str] = []
    non_matching_columns: list[str] = []

    for row in table_rows:
        field_name = _norm(row["Veldnaam"])
        metadata_value = str(row[metadata_column]).strip().lower()

        if metadata_value == "true":
            matching_columns.append(field_name)
        elif metadata_value == "false":
            non_matching_columns.append(field_name)
        # If neither true nor false, do nothing (skip the column)

    # Add matching columns to properties if not empty
    if matching_columns:
        properties[property_key] = ",".join(matching_columns)

    # Add non-matching columns to properties if not empty and key provided
    if non_matching_columns and non_matching_property_key:
        properties[non_matching_property_key] = ",".join(non_matching_columns)

    return matching_columns, non_matching_columns


def _process_business_keys(
    properties: dict[str, str], business_keys: dict[str, list[str]]
) -> None:
    """Process business keys and add to properties. This functions checks for the values single_keys and composite_key_*.
    If single_keys, the column names are added to the business_keys property. If composite_key_*,
    the column names are added to the business_keys property."""

    key_info: list[str] = []
    for key_type, columns in business_keys.items():
        if key_type == "single_keys":
            properties["business_keys"] = ",".join(columns)
            key_info.append(f"Single keys: {', '.join(columns)}")
        else:
            # Composite key
            properties["business_keys"] = ",".join(columns)
            key_info.append(f"{key_type}: {', '.join(columns)}")

    print(f"  → Business keys: {'; '.join(key_info)}")


def _add_metadata_property_value(
    properties: dict[str, str], table_rows: list, column_name: str
) -> None:
    """Add metadata property value if it exists. This functions checks for the value of the column_name in the table_rows list.
    If the value is not None, the actual value in the cell is added to the properties dictionary."""

    # Extract metadata value from already collected table rows
    if table_rows and len(table_rows) > 0:
        value = table_rows[0][column_name]
        if value is not None:
            value_str = str(value).strip()
            if value_str:
                properties[column_name] = value_str

"""
Utilities for managing change requests and review/approval workflow.
"""

from __future__ import annotations

import uuid
import pandas as pd
from typing import Optional, Dict, Any, List

from utils.sql_utils import (
    sql_query,
    execute_query,
    insert_data,
    bulk_insert_data,
    get_current_user,
    get_current_timestamp,
    get_table_columns,
)
from config.constants import (
    CR_ID_COL,
    CR_STATUS_PENDING,
    CR_STATUS_APPROVED,
    CR_STATUS_REJECTED,
    CR_STATUS_CANCELLED,
    META_SCHEMA_NAME,
    META_CR_TABLE_NAME,
    AUDIT_COLS,
)


def _quote_identifier(identifier: str) -> str:
    clean = identifier.replace("`", "")
    return f"`{clean}`"


def _meta_table_fqn(catalog: str) -> str:
    return (
        f"{_quote_identifier(catalog)}."
        f"{_quote_identifier(META_SCHEMA_NAME)}."
        f"{_quote_identifier(META_CR_TABLE_NAME)}"
    )


def ensure_meta_objects(catalog: str) -> None:
    """
    Ensure the change request metadata schema and table exist.
    Creates them if they don't exist.
    """
    schema_fqn = f"{_quote_identifier(catalog)}.{_quote_identifier(META_SCHEMA_NAME)}"
    
    # Create schema if it doesn't exist
    try:
        execute_query(f"CREATE SCHEMA IF NOT EXISTS {schema_fqn}")
    except Exception:
        pass  # Schema might already exist
    
    # Create change request metadata table if it doesn't exist
    meta_table_fqn = f"{schema_fqn}.{_quote_identifier(META_CR_TABLE_NAME)}"
    
    create_meta_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {meta_table_fqn} (
        cr_id STRING NOT NULL,
        target_table STRING NOT NULL,
        change_type STRING NOT NULL,
        submitted_by STRING NOT NULL,
        submitted_ts TIMESTAMP NOT NULL,
        approved_by STRING,
        approved_ts TIMESTAMP,
        rejected_by STRING,
        rejected_ts TIMESTAMP,
        status STRING NOT NULL,
        note STRING,
        row_count INT NOT NULL,
        rejection_reason STRING
    )
    USING DELTA
    TBLPROPERTIES (
        'delta.autoOptimize.optimizeWrite' = 'true',
        'delta.autoOptimize.autoCompact' = 'true'
    )
    """
    
    try:
        execute_query(create_meta_table_sql)
    except Exception:
        pass  # Table might already exist


def ensure_staging_table(target_table_fqn: str, cr_id_col: str, audit_cols: List[str]) -> str:
    """
    Ensure a staging table exists for the given target table.
    Creates it if it doesn't exist by copying the target table's schema.
    
    Args:
        target_table_fqn: Fully qualified name of the target table (may include backticks)
        cr_id_col: Name of the change request ID column to add
        audit_cols: List of audit columns (these will be included in staging)
        
    Returns:
        Fully qualified name of the staging table
    """
    # Parse the table name to handle backticks properly
    # Input format: `catalog`.`schema`.`table` or catalog.schema.table
    # We need to extract components and add _staging to the table name
    
    # Remove backticks and split by `.`
    clean_name = target_table_fqn.replace('`', '')
    parts = clean_name.split('.')
    
    if len(parts) == 3:
        catalog, schema, table = parts
        # Add _staging to the table name
        staging_table = f"{table}_staging"
        # Reconstruct with backticks
        staging_fqn = f"`{catalog}`.`{schema}`.`{staging_table}`"
    elif len(parts) == 2:
        schema, table = parts
        staging_table = f"{table}_staging"
        staging_fqn = f"`{schema}`.`{staging_table}`"
    else:
        # Fallback: simple append (shouldn't happen, but safe)
        staging_fqn = f"{target_table_fqn}_staging"
    
    # Check if staging table already exists
    try:
        check_query = f"DESCRIBE TABLE {staging_fqn}"
        sql_query(check_query)
        # Table exists, return it
        return staging_fqn
    except Exception:
        # Table doesn't exist, create it
        pass
    
    # Get target table schema - use DESCRIBE TABLE to get all columns
    target_cols_df = get_table_columns(target_table_fqn)
    
    # Build column definitions - include ALL columns from target table
    # We include audit columns because the data being inserted will have them
    col_defs = []
    for _, row in target_cols_df.iterrows():
        col_name = row["col_name"]
        col_type = row["data_type"]
        
        # Skip if this is already the CR_ID column (shouldn't happen, but safety check)
        if col_name == cr_id_col:
            continue
            
        col_defs.append(f"`{col_name}` {col_type}")
    
    # Add CR_ID column at the beginning
    col_defs.insert(0, f"`{cr_id_col}` STRING NOT NULL")
    
    # Create staging table
    create_staging_sql = f"""
    CREATE TABLE {staging_fqn} (
        {', '.join(col_defs)}
    )
    USING DELTA
    TBLPROPERTIES (
        'delta.autoOptimize.optimizeWrite' = 'true',
        'delta.autoOptimize.autoCompact' = 'true'
    )
    """
    
    execute_query(create_staging_sql)
    return staging_fqn


def create_change_request(
    catalog: str,
    target_table: str,
    submitted_by: str,
    change_type: str,
    note: str,
    rows_df: pd.DataFrame,
) -> str:
    """
    Create a change request: insert metadata and write rows to staging table.
    
    Args:
        catalog: Catalog name
        target_table: Fully qualified target table name
        submitted_by: User who submitted the change
        change_type: Type of change ('row', 'bulk', 'update', 'delete')
        note: Optional note/comment from submitter
        rows_df: DataFrame containing the rows to be reviewed
        
    Returns:
        Change request ID (UUID string)
    """
    # Ensure metadata objects exist
    ensure_meta_objects(catalog)
    
    # Generate CR ID
    cr_id = str(uuid.uuid4())
    submitted_ts = get_current_timestamp()
    
    # Ensure staging table exists
    target_table_fqn = target_table
    staging_fqn = ensure_staging_table(target_table_fqn, CR_ID_COL, AUDIT_COLS)
    
    # Add CR_ID to rows
    rows_with_cr = rows_df.copy()
    rows_with_cr[CR_ID_COL] = cr_id
    
    # Reorder columns to put CR_ID first
    cols = [CR_ID_COL] + [c for c in rows_with_cr.columns if c != CR_ID_COL]
    rows_with_cr = rows_with_cr[cols]
    
    # Insert rows into staging table
    bulk_insert_data(staging_fqn, rows_with_cr)
    
    # Insert metadata record - escape single quotes in strings
    meta_fqn = _meta_table_fqn(catalog)
    submitted_by_escaped = submitted_by.replace("'", "''")
    target_table_escaped = target_table.replace("'", "''")
    change_type_escaped = change_type.replace("'", "''")
    note_escaped = (note or "").replace("'", "''")
    
    meta_data = {
        "cr_id": cr_id,
        "target_table": target_table_escaped,
        "change_type": change_type_escaped,
        "submitted_by": submitted_by_escaped,
        "submitted_ts": submitted_ts,
        "approved_by": None,
        "approved_ts": None,
        "rejected_by": None,
        "rejected_ts": None,
        "status": CR_STATUS_PENDING,
        "note": note_escaped,
        "row_count": len(rows_df),
        "rejection_reason": None,
    }
    insert_data(meta_fqn, meta_data)
    
    return cr_id


def get_change_requests(
    catalog: str,
    target_table: Optional[str] = None,
    status: Optional[str] = None,
    submitted_by: Optional[str] = None,
) -> pd.DataFrame:
    """
    Query change request metadata.
    
    Args:
        catalog: Catalog name
        target_table: Optional filter by target table
        status: Optional filter by status ('pending', 'approved', 'rejected')
        submitted_by: Optional filter by submitter
        
    Returns:
        DataFrame with change request metadata
    """
    meta_fqn = _meta_table_fqn(catalog)
    
    where_clauses = []
    if target_table:
        target_table_escaped = target_table.replace("'", "''")
        where_clauses.append(f"target_table = '{target_table_escaped}'")
    if status:
        where_clauses.append(f"status = '{status}'")
    if submitted_by:
        submitted_by_escaped = submitted_by.replace("'", "''")
        where_clauses.append(f"submitted_by = '{submitted_by_escaped}'")
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    query = f"""
    SELECT *
    FROM {meta_fqn}
    WHERE {where_sql}
    ORDER BY submitted_ts DESC
    """
    
    return sql_query(query)


def get_unique_tables(catalog: str) -> List[str]:
    """
    Get list of unique target tables from change requests.
    
    Args:
        catalog: Catalog name
        
    Returns:
        List of unique table names (sorted)
    """
    meta_fqn = _meta_table_fqn(catalog)
    
    try:
        query = f"""
        SELECT DISTINCT target_table
        FROM {meta_fqn}
        ORDER BY target_table
        """
        result = sql_query(query)
        if not result.empty:
            return result["target_table"].tolist()
        return []
    except Exception:
        return []


def get_unique_submitters(catalog: str) -> List[str]:
    """
    Get list of unique submitters from change requests.
    
    Args:
        catalog: Catalog name
        
    Returns:
        List of unique submitter names (sorted)
    """
    meta_fqn = _meta_table_fqn(catalog)
    
    try:
        query = f"""
        SELECT DISTINCT submitted_by
        FROM {meta_fqn}
        ORDER BY submitted_by
        """
        result = sql_query(query)
        if not result.empty:
            return result["submitted_by"].tolist()
        return []
    except Exception:
        return []


def get_staging_rows(catalog: str, target_table: str, cr_id: str) -> pd.DataFrame:
    """
    Get all staging rows for a specific change request.
    
    Args:
        catalog: Catalog name (not used but kept for consistency)
        target_table: Fully qualified target table name (may include backticks)
        cr_id: Change request ID
        
    Returns:
        DataFrame with staging rows (excluding CR_ID column for display)
    """
    # Parse the table name to handle backticks properly
    clean_name = target_table.replace('`', '')
    parts = clean_name.split('.')
    
    if len(parts) == 3:
        catalog_part, schema, table = parts
        staging_table = f"{table}_staging"
        staging_fqn = f"`{catalog_part}`.`{schema}`.`{staging_table}`"
    elif len(parts) == 2:
        schema, table = parts
        staging_table = f"{table}_staging"
        staging_fqn = f"`{schema}`.`{staging_table}`"
    else:
        staging_fqn = f"{target_table}_staging"
    
    query = f"""
    SELECT *
    FROM {staging_fqn}
    WHERE {CR_ID_COL} = '{cr_id}'
    ORDER BY {CR_ID_COL}
    """
    
    return sql_query(query)


def approve_change_request(
    catalog: str,
    target_table: str,
    cr_id: str,
    approved_by: str,
) -> None:
    """
    Approve a change request: move rows from staging to target table and update metadata.
    
    Args:
        catalog: Catalog name
        target_table: Fully qualified target table name (may include backticks)
        cr_id: Change request ID
        approved_by: User who approved the change
        
    Raises:
        ValueError: If the approver is the same as the submitter (self-approval not allowed)
    """
    meta_fqn = _meta_table_fqn(catalog)
    
    # First, check who submitted this change request to prevent self-approval
    check_query = f"""
    SELECT submitted_by, status
    FROM {meta_fqn}
    WHERE cr_id = '{cr_id}'
    """
    cr_info = sql_query(check_query)
    
    if cr_info.empty:
        raise ValueError(f"Change request {cr_id} not found")
    
    submitted_by = str(cr_info.iloc[0]["submitted_by"])
    current_status = str(cr_info.iloc[0]["status"])
    
    # Prevent self-approval
    if submitted_by == approved_by:
        raise ValueError(
            f"You cannot approve your own change request. "
            f"This change request was submitted by {submitted_by}. "
            f"Please ask another user to review and approve it."
        )
    
    # Check if already processed
    if current_status != CR_STATUS_PENDING:
        raise ValueError(
            f"Change request {cr_id} is already {current_status} and cannot be approved."
        )
    
    # Parse the table name to handle backticks properly
    clean_name = target_table.replace('`', '')
    parts = clean_name.split('.')
    
    if len(parts) == 3:
        catalog_part, schema, table = parts
        staging_table = f"{table}_staging"
        staging_fqn = f"`{catalog_part}`.`{schema}`.`{staging_table}`"
    elif len(parts) == 2:
        schema, table = parts
        staging_table = f"{table}_staging"
        staging_fqn = f"`{schema}`.`{staging_table}`"
    else:
        staging_fqn = f"{target_table}_staging"
    
    approved_ts = get_current_timestamp()
    
    # Get staging rows (excluding CR_ID)
    staging_rows = get_staging_rows(catalog, target_table, cr_id)
    
    if staging_rows.empty:
        raise ValueError(f"No staging rows found for CR {cr_id}")
    
    # Remove CR_ID column before inserting into target table
    rows_to_insert = staging_rows.drop(columns=[CR_ID_COL])
    
    # Insert into target table
    bulk_insert_data(target_table, rows_to_insert)
    
    # Update metadata - escape single quotes in approved_by
    approved_by_escaped = approved_by.replace("'", "''")
    update_sql = f"""
    UPDATE {meta_fqn}
    SET 
        status = '{CR_STATUS_APPROVED}',
        approved_by = '{approved_by_escaped}',
        approved_ts = TIMESTAMP '{approved_ts}'
    WHERE cr_id = '{cr_id}'
    """
    execute_query(update_sql)
    
    # Optionally: clean up staging rows (or keep for audit)
    # For now, we'll keep them for audit trail
    # delete_sql = f"DELETE FROM {staging_fqn} WHERE {CR_ID_COL} = '{cr_id}'"
    # execute_query(delete_sql)


def reject_change_request(
    catalog: str,
    target_table: str,
    cr_id: str,
    rejected_by: str,
    reason: str = "",
) -> None:
    """
    Reject a change request: update metadata status without moving data.
    
    Args:
        catalog: Catalog name
        target_table: Fully qualified target table name (for consistency)
        cr_id: Change request ID
        rejected_by: User who rejected the change
        reason: Optional rejection reason
        
    Raises:
        ValueError: If the rejector is the same as the submitter (self-rejection not allowed)
    """
    meta_fqn = _meta_table_fqn(catalog)
    
    # First, check who submitted this change request to prevent self-rejection
    check_query = f"""
    SELECT submitted_by, status
    FROM {meta_fqn}
    WHERE cr_id = '{cr_id}'
    """
    cr_info = sql_query(check_query)
    
    if cr_info.empty:
        raise ValueError(f"Change request {cr_id} not found")
    
    submitted_by = str(cr_info.iloc[0]["submitted_by"])
    current_status = str(cr_info.iloc[0]["status"])
    
    # Prevent self-rejection (same as self-approval - requires another user)
    if submitted_by == rejected_by:
        raise ValueError(
            f"You cannot reject your own change request. "
            f"This change request was submitted by {submitted_by}. "
            f"Please ask another user to review it, or cancel it if you no longer need it."
        )
    
    # Check if already processed
    if current_status != CR_STATUS_PENDING:
        raise ValueError(
            f"Change request {cr_id} is already {current_status} and cannot be rejected."
        )
    
    rejected_ts = get_current_timestamp()
    
    # Escape single quotes in reason
    reason_escaped = reason.replace("'", "''") if reason else ""
    
    # Update metadata - escape single quotes
    rejected_by_escaped = rejected_by.replace("'", "''")
    update_sql = f"""
    UPDATE {meta_fqn}
    SET 
        status = '{CR_STATUS_REJECTED}',
        rejected_by = '{rejected_by_escaped}',
        rejected_ts = TIMESTAMP '{rejected_ts}',
        rejection_reason = '{reason_escaped}'
    WHERE cr_id = '{cr_id}'
    """
    execute_query(update_sql)
    
    # Staging rows remain for audit trail


def cancel_change_request(
    catalog: str,
    cr_id: str,
    cancelled_by: str,
) -> None:
    """
    Cancel a change request (e.g., by the submitter).
    
    Args:
        catalog: Catalog name
        cr_id: Change request ID
        cancelled_by: User who cancelled the change
    """
    meta_fqn = _meta_table_fqn(catalog)
    
    update_sql = f"""
    UPDATE {meta_fqn}
    SET status = '{CR_STATUS_CANCELLED}'
    WHERE cr_id = '{cr_id}' AND status = '{CR_STATUS_PENDING}'
    """
    execute_query(update_sql)

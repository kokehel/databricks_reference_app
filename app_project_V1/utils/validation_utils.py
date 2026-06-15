"""
Validation helper functions for data entry actions.
Extracted to reduce duplication and improve maintainability.
"""

from typing import Dict, List, Any, Optional, Callable
import pandas as pd
import datetime

from utils.data_utils import (
    _is_bool,
    _is_date,
    _is_empty,
    _is_float,
    _is_int,
)


def validate_business_key_uniqueness(
    new_data: pd.DataFrame,
    existing_data: pd.DataFrame,
    business_keys: List[str],
    key_col: str,
    col_type_map: Dict[str, str],
    exclude_key: Optional[int] = None,
) -> List[str]:
    """
    Validate that business keys are unique against existing data.
    
    Args:
        new_data: DataFrame with new rows to validate
        existing_data: DataFrame with existing rows to check against
        business_keys: List of business key column names
        key_col: Name of the primary key column
        col_type_map: Mapping of column names to data types
        exclude_key: Optional key to exclude from existing data (for updates)
        
    Returns:
        List of error messages (empty if no conflicts)
    """
    errors = []
    
    if not business_keys or new_data.empty:
        return errors
    
    # Filter existing data if excluding a key (for updates)
    df_check = existing_data.copy()
    if exclude_key is not None and not df_check.empty:
        df_check = df_check[df_check[key_col] != exclude_key]
    
    if df_check.empty:
        return errors
    
    # Check each new row against existing data
    for idx, new_row in new_data.iterrows():
        # Only check if all business keys are present and non-empty
        if not all(
            (bk in new_row) and (not _is_empty(new_row[bk]))
            for bk in business_keys
        ):
            continue
        
        # Build mask for matching business keys
        mask = pd.Series(True, index=df_check.index)
        
        for bk in business_keys:
            v = new_row.get(bk)
            
            if _is_int(col=bk, col_type_map=col_type_map):
                left = pd.to_numeric(df_check[bk], errors="coerce")
                right = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
                mask &= left.eq(right)
            elif _is_float(col=bk, col_type_map=col_type_map):
                left = pd.to_numeric(df_check[bk], errors="coerce")
                try:
                    right = float(v)
                except Exception:
                    right = None
                mask &= left.eq(right)
            elif _is_date(col=bk, col_type_map=col_type_map):
                left = pd.to_datetime(df_check[bk], errors="coerce").dt.normalize()
                right = pd.to_datetime(v, errors="coerce")
                if pd.notna(right):
                    right = pd.Timestamp(right).normalize()
                mask &= left.eq(right)
            else:
                left = (
                    df_check[bk]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .str.casefold()
                )
                right = (
                    str(v).strip().casefold()
                    if v is not None
                    else ""
                )
                mask &= left == right
        
        conflicts = df_check[mask]
        if not conflicts.empty:
            conflict_keys = ", ".join(
                map(str, conflicts[key_col].tolist()[:10])
            )
            errors.append(
                f"Row {idx + 1}: Unique constraint violated for {', '.join(business_keys)}; "
                f"matches existing key(s): {conflict_keys}"
            )
    
    return errors


def validate_date_range_constraints(
    new_data: pd.DataFrame,
    existing_data: pd.DataFrame,
    validity_key: str,
    valid_from: str,
    valid_to: str,
    key_col: str,
    all_cols: List[str],
    date_range_constraint_func: Callable,
    exclude_key: Optional[int] = None,
) -> List[str]:
    """
    Validate date range constraints for validity periods.
    
    Args:
        new_data: DataFrame with new rows to validate
        existing_data: DataFrame with existing rows to check against
        validity_key: Column name for the validity key
        valid_from: Column name for start date
        valid_to: Column name for end date
        key_col: Name of the primary key column
        all_cols: List of all column names
        exclude_key: Optional key to exclude from existing data (for updates)
        date_range_constraint_func: Function to check date range conflicts
        
    Returns:
        List of error messages (empty if no conflicts)
    """
    errors = []
    
    if not validity_key or new_data.empty:
        return errors
    
    # Filter existing data if excluding a key (for updates)
    df_check = existing_data.copy()
    if exclude_key is not None and not df_check.empty:
        df_check = df_check[df_check[key_col] != exclude_key]
    
    # Combine new and existing data for conflict checking
    combined = pd.concat([df_check, new_data], ignore_index=True)
    
    conflicts = date_range_constraint_func(
        data=combined,
        validity_key=validity_key,
        start_date=valid_from,
        end_date=valid_to,
    )
    
    if conflicts:
        for idx, new_row in new_data.iterrows():
            conflict_key = new_row[validity_key]
            new_row_key = new_row[key_col]
            conflict_keys = ", ".join(
                str(row.iloc[all_cols.index(key_col)])
                for conflict in conflicts
                for row in conflict
                if row.iloc[all_cols.index(key_col)] != new_row_key
            )
            if conflict_keys:
                errors.append(
                    f"Row {idx + 1}: Date range constraint violated for {validity_key} {conflict_key}; "
                    f"overlaps with existing key(s): {conflict_keys}"
                )
    
    return errors


def validate_single_row_types(
    row: Dict[str, Any],
    audit_cols: List[str],
    not_editable_cols: List[str],
    not_null_cols: List[str],
    col_type_map: Dict[str, str],
) -> List[str]:
    """
    Validate data types and required fields for a single row.
    
    Args:
        row: Dictionary representing a single row
        audit_cols: List of audit column names to skip
        not_editable_cols: List of non-editable column names to skip
        not_null_cols: List of required column names
        col_type_map: Mapping of column names to data types
        
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    for col, val in row.items():
        if col in audit_cols or col in not_editable_cols:
            continue
        
        # Required (not-null) constraints
        if col in not_null_cols and _is_empty(val):
            errors.append(f"{col}: value is required and cannot be empty")
        
        # Type validation
        if _is_float(col=col, col_type_map=col_type_map):
            try:
                float(val)
            except Exception:
                errors.append(f"{col}: expected a decimal number")
        elif _is_int(col=col, col_type_map=col_type_map):
            if val is not None:
                try:
                    int(val)
                except Exception:
                    errors.append(f"{col}: expected an integer")
        elif _is_date(col=col, col_type_map=col_type_map):
            if not isinstance(
                val,
                (datetime.date, datetime.datetime, pd.Timestamp),
            ):
                errors.append(f"{col}: expected a date")
        elif _is_bool(col=col, col_type_map=col_type_map):
            if not isinstance(val, bool):
                errors.append(f"{col}: expected TRUE/FALSE")
    
    return errors


def inject_audit_columns(
    df: pd.DataFrame,
    upload_ts_col: str,
    upload_version_col: str,
    upload_user_col: str,
    upload_file_name_col: str,
    latest_version: Optional[int] = None,
    file_name: str = "",
) -> pd.DataFrame:
    """
    Inject audit columns into a DataFrame.
    
    Args:
        df: DataFrame to add audit columns to
        upload_ts_col: Name of upload timestamp column
        upload_version_col: Name of version column
        upload_user_col: Name of user column
        upload_file_name_col: Name of file name column
        latest_version: Latest version number (will be calculated if None)
        file_name: Name of uploaded file (if applicable)
        
    Returns:
        DataFrame with audit columns added
    """
    from utils.sql_utils import get_current_timestamp, get_current_user
    
    df = df.copy()
    
    df[upload_ts_col] = get_current_timestamp()
    if latest_version is not None:
        df[upload_version_col] = latest_version
    df[upload_user_col] = get_current_user()
    df[upload_file_name_col] = file_name
    
    return df


def get_next_version(table: str, upload_version_col: str) -> int:
    """
    Get the next version number for a table.
    
    Args:
        table: Table name
        upload_version_col: Name of version column
        
    Returns:
        Next version number (1 if table is empty)
    """
    from utils.sql_utils import sql_query
    
    try:
        latest_version_query = f"SELECT MAX({upload_version_col}) as max_version FROM {table}"
        latest_version_result = sql_query(latest_version_query)
        latest_version = None
        if (
            not latest_version_result.empty
            and "max_version" in latest_version_result.columns
        ):
            latest_version = latest_version_result["max_version"].iloc[0]
        next_version = (
            int(latest_version) + 1
            if (latest_version is not None and pd.notna(latest_version))
            else 1
        )
        return next_version
    except Exception:
        return 1

"""Utility helpers for Databricks SQL that run **as the signed‑in user**."""

from __future__ import annotations

import os
from typing import Dict, Any

import datetime as dt
from decimal import Decimal
import numpy as np

import pandas as pd
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config
from config.runtime import require_warehouse_id

__all__ = [
    "sql_query",
    "execute_query",
    "insert_data",
    "bulk_insert_data",
    "get_table_columns",
    "get_current_user",
    "get_current_timestamp",
    "get_table_schema",
    "clean_df",
    "validate_df",
    "get_table_constraints",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_user_token() -> str:
    token = None
    try:
        token = st.context.headers.get("x-forwarded-access-token")
    except Exception:
        pass
    if not token:
        raise RuntimeError(
            "Missing X-Forwarded-Access-Token header. This code must run inside a Databricks App that has the `sql` user-authorization scope enabled."
        )
    return token


@st.cache_resource(ttl=600, show_spinner="Connecting to warehouse…")
def _connect(user_token: str) -> sql.Connection:  # type: ignore[name-defined]
    cfg = Config()

    warehouse_id = require_warehouse_id()
    http_path = f"/sql/1.0/warehouses/{warehouse_id}"

    try:
        connection = sql.connect(
            server_hostname=cfg.host,
            http_path=http_path,
            access_token=user_token,
        )
        return connection
    except Exception as e:
        raise RuntimeError(
            f"Failed to connect to warehouse {warehouse_id}: {str(e)}"
        )


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def sql_query(query: str) -> pd.DataFrame:
    with _connect(_get_user_token()).cursor() as cur:  # type: ignore[attr-defined]
        cur.execute(query)
        return cur.fetchall_arrow().to_pandas()


def execute_query(query: str) -> None:
    with _connect(_get_user_token()).cursor() as cur:  # type: ignore[attr-defined]
        cur.execute(query)


# ---------------------------------------------------------------------------
# Convenience helpers for the Streamlit CRUD UI
# ---------------------------------------------------------------------------


def _serialize_value(v):
    """
    Return a literal for Databricks SQL.
    Handles None / pd.NA, dates, booleans, numbers, and strings.
    """
    # ---------- NULLs ----------
    if (
        v is None
        or (isinstance(v, float) and pd.isna(v))
        or (v is pd.NA)
        or pd.isna(v)
    ):
        return "NULL"
    if isinstance(v, str):
        s0 = v.strip()
        if s0 == "" or s0.lower() in {"null", "na", "nan"}:
            return "NULL"

    # ---------- BOOLEAN ----------
    if isinstance(v, (bool, np.bool_)):
        return "TRUE" if v else "FALSE"

    # ---------- NUMBERS (leave un-quoted) ----------
    if isinstance(v, (int, float, Decimal, np.integer, np.floating)):
        return str(v)

    # ---------- STRING fallback (single-quote & escape) ----------
    s = str(v).replace("'", "''")
    s = " ".join(s.split())  # collapse weird whitespace
    return f"'{s}'"


def insert_data(table: str, data: Dict[str, Any]) -> None:
    cols = ", ".join(f"`{col}`" for col in data.keys())
    vals = ", ".join(_serialize_value(v) for v in data.values())
    execute_query(f"INSERT INTO {table} ({cols}) VALUES ({vals})")


def bulk_insert_data(
    table: str, df: pd.DataFrame, batch_size: int = 10000
) -> None:
    if df.empty:
        return
    cols = ", ".join(f"`{col}`" for col in df.columns)
    for start in range(0, len(df), batch_size):
        batch = df.iloc[start : start + batch_size]
        values_sql = ", ".join(
            "(" + ", ".join(_serialize_value(v) for v in row) + ")"
            for row in batch.itertuples(index=False)
        )
        execute_query(f"INSERT INTO {table} ({cols}) VALUES {values_sql}")


# ---------------------------------------------------------------------------
# Added helpers
# ---------------------------------------------------------------------------


def get_table_columns(table: str) -> pd.DataFrame:
    """Return DataFrame with column names/types for `table`.
    We use Databricks `DESCRIBE TABLE` output and filter out partition/metadata rows.
    Columns: col_name, data_type, comment.
    """
    df = sql_query(f"DESCRIBE TABLE {table}")
    df = df.rename(
        columns={
            df.columns[0]: "col_name",
            df.columns[1]: "data_type",
            df.columns[2]: "comment",
        }
    )
    df = df[df["col_name"].notna() & ~df["col_name"].str.startswith("#")]
    return df.reset_index(drop=True)


def get_current_user() -> str:
    try:
        df = sql_query("SELECT current_user() AS u")
        return str(df.iloc[0, 0])
    except Exception:  # fallback
        return "unknown_user"


def get_current_timestamp() -> str:
    try:
        df = sql_query("SELECT current_timestamp() AS ts")
        # return ISO string; arrow->pandas usually gives datetime64
        ts = pd.to_datetime(df.iloc[0, 0])
        return ts.isoformat()
    except Exception:
        return pd.Timestamp.utcnow().isoformat()


def get_table_schema(table: str) -> dict[str, str]:
    """
    Return {column_name: data_type} for a UC table.
    Ignores partition/metadata rows that DESCRIBE TABLE adds.
    """
    df = sql_query(f"DESCRIBE TABLE {table}")

    # Keep only the real columns (DESCRIBE outputs # Header rows)
    df = df[~df["col_name"].str.startswith("#")]  # Filter out metadata rows

    # Build the mapping
    return dict(zip(df["col_name"], df["data_type"]))


# Re-use the same two patterns
_DDMMYYYY = re.compile(r"^\s*(\d{1,2})[-/](\d{1,2})[-/](\d{4})\s*$")
_YYYYMMDD = re.compile(r"^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*$")
_VALID_BOOL_VALUES = {"true", "false", "1", "0"}


def _normalize_text_series(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def _parse_date_safe(val: str):
    """
    Convert a string to datetime.date.
    Supports years 1-9999 and formats dd-MM-yyyy, yyyy-MM-dd (with - or /).
    Returns pd.NA if unparseable.
    """
    if pd.isna(val) or val == "":
        return pd.NA

    s = str(val).strip()

    # 1️⃣ Fast path: pandas (quick for normal year range)
    try:
        return pd.to_datetime(s, dayfirst=True, errors="raise").date()
    except Exception:
        pass

    # 2️⃣ Manual fallback (handles 9999, 0001, etc.)
    m = _DDMMYYYY.match(s) or _YYYYMMDD.match(s)
    if not m:
        return pd.NA

    if m.re is _DDMMYYYY:
        d, mth, y = map(int, m.groups())
    else:  # _YYYYMMDD
        y, mth, d = map(int, m.groups())

    try:
        return dt.date(y, mth, d)
    except ValueError:
        return pd.NA


def _coerce_date_series(series: pd.Series) -> pd.Series:
    """
    Convert a whole Series to datetime.date values with a vectorized fast path.
    Falls back to scalar parsing only for entries that remain unresolved.
    """
    text = _normalize_text_series(series)
    empty_mask = text.isna() | text.eq("")

    result = pd.Series(pd.NA, index=series.index, dtype="object")
    if empty_mask.all():
        return result

    candidates = text[~empty_mask]

    year_first = pd.to_datetime(
        candidates,
        format="%Y-%m-%d",
        errors="coerce",
    )
    unresolved = year_first.isna()
    if unresolved.any():
        alt_year_first = pd.to_datetime(
            candidates[unresolved].str.replace("/", "-", regex=False),
            format="%Y-%m-%d",
            errors="coerce",
        )
        year_first.loc[unresolved] = alt_year_first

    day_first = pd.to_datetime(
        candidates,
        format="%d-%m-%Y",
        errors="coerce",
    )
    unresolved = day_first.isna()
    if unresolved.any():
        alt_day_first = pd.to_datetime(
            candidates[unresolved].str.replace("/", "-", regex=False),
            format="%d-%m-%Y",
            errors="coerce",
        )
        day_first.loc[unresolved] = alt_day_first

    combined = year_first.fillna(day_first)
    resolved_mask = combined.notna()
    if resolved_mask.any():
        result.loc[candidates.index[resolved_mask]] = combined.loc[
            resolved_mask
        ].dt.date.to_numpy()

    remaining_idx = candidates.index[~resolved_mask]
    if len(remaining_idx) > 0:
        result.loc[remaining_idx] = candidates.loc[remaining_idx].map(
            _parse_date_safe
        )

    return result


def clean_df(df: pd.DataFrame, schema: dict[str, str]):
    df_fixed = df.copy()
    log = {}

    for col, schema_type in schema.items():
        if col not in df_fixed.columns:
            continue

        dtype = schema_type.upper()

        if dtype == "DATE":
            source = df_fixed[col]
            cleaned_dates = _coerce_date_series(source)
            df_fixed[col] = cleaned_dates
            fixed = 0
            if fixed:
                log[col] = fixed

        elif dtype in {"INT", "BIGINT"}:
            before_valid = (
                pd.to_numeric(df_fixed[col], errors="coerce").notna().sum()
            )

            df_fixed[col] = pd.to_numeric(
                df_fixed[col], errors="coerce"
            ).astype("Int64")  # float or int with NaN  # => nullable integer

            fixed = df_fixed[col].notna().sum() - before_valid
            if fixed:
                log[col] = fixed

        elif dtype in {"FLOAT", "DOUBLE", "DECIMAL"}:
            before = (
                pd.to_numeric(
                    df_fixed[col]
                    .astype(str)
                    .str.replace(",", ".", regex=False),
                    errors="coerce",
                )
                .notna()
                .sum()
            )

            df_fixed[col] = (
                df_fixed[col]
                .astype(str)
                .str.replace(",", ".", regex=False)
                .pipe(pd.to_numeric, errors="coerce")
            )

            fixed = df_fixed[col].notna().sum() - before
            if fixed:
                log[col] = fixed

    return df_fixed, log


_DEC_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")  # dot *or* comma decimals


def validate_df(df: pd.DataFrame, schema: dict[str, str]):
    problems = {}

    for col, schema_type in schema.items():
        if col not in df.columns:
            continue

        expected = schema_type.upper()
        text = _normalize_text_series(df[col])
        present_mask = text.notna() & text.ne("")
        if not present_mask.any():
            continue

        msgs = []

        if expected == "DATE":
            invalid_mask = present_mask & df[col].isna()
            if invalid_mask.any():
                bad_values = text[invalid_mask]
                msgs = [
                    f"Row {int(idx) + 1}: '{value}' - not a valid DATE"
                    for idx, value in bad_values.items()
                ]

        elif expected in {"INT", "BIGINT"}:
            invalid_mask = present_mask & ~text.str.fullmatch(r"-?\d+")
            if invalid_mask.any():
                bad_values = text[invalid_mask]
                msgs = [
                    f"Row {int(idx) + 1}: '{value}' - expected {expected}"
                    for idx, value in bad_values.items()
                ]

        elif expected in {"FLOAT", "DOUBLE", "DECIMAL"}:
            invalid_mask = present_mask & ~text.str.fullmatch(_DEC_RE)
            if invalid_mask.any():
                bad_values = text[invalid_mask]
                msgs = [
                    f"Row {int(idx) + 1}: '{value}' - expected decimal number"
                    for idx, value in bad_values.items()
                ]

        elif expected == "BOOLEAN":
            invalid_mask = present_mask & ~text.str.lower().isin(
                _VALID_BOOL_VALUES
            )
            if invalid_mask.any():
                bad_values = text[invalid_mask]
                msgs = [
                    f"Row {int(idx) + 1}: '{value}' - expected BOOLEAN"
                    for idx, value in bad_values.items()
                ]

        if msgs:
            problems[col] = msgs

    return problems


@st.cache_data(ttl=300)
def _get_table_properties(table: str) -> dict[str, str]:
    """
    Return Delta table properties as a plain dict using DESCRIBE DETAIL.
    """
    try:
        df = sql_query(f"DESCRIBE DETAIL {table}")
        if df is None or df.empty or "properties" not in df.columns:
            return {}

        raw = df.at[0, "properties"]

        # List/tuple of key/value pairs or {'key':..., 'value':...}
        if isinstance(raw, (list, tuple)):
            out: dict[str, str] = {}
            for entry in raw:
                if isinstance(entry, dict) and "key" in entry:
                    k, v = entry.get("key"), entry.get("value")
                elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                    k, v = entry[0], entry[1]
                else:
                    continue
                if k is not None:
                    out[str(k)] = "" if v is None else str(v)
            return out

        return {}
    except Exception:
        return {}


def get_table_constraints(
    table: str, all_cols: list[str]
) -> tuple[
    list[str],
    list[str],
    list[str],
    bool,
    bool,
    bool,
    str | None,
    str | None,
    str | None,
]:
    """
    Extract not-null and business-key (unique) columns from Delta table properties.

    Returns:
      (
        not_null_columns,
        business_keys,
        not_editable_columns,
        single_insert,
        bulk_insert,
        review_required,
        valid_from,
        valid_to,
        validity_key,
      )
    Lists are filtered to existing columns in `all_cols`.
    """
    props = _get_table_properties(table)

    def _split_csv(val: str | None) -> list[str]:
        if not val:
            return []
        return [c.strip() for c in str(val).split(",") if c and c.strip()]

    not_null_cols = [
        c for c in _split_csv(props.get("not_null_columns")) if c in all_cols
    ]
    business_keys = [
        c for c in _split_csv(props.get("business_keys")) if c in all_cols
    ]
    not_editable = [
        c for c in _split_csv(props.get("not_editable")) if c in all_cols
    ]
    valid_from = next(
        (c for c in _split_csv(props.get("valid_from")) if c in all_cols), None
    )
    valid_to = next(
        (c for c in _split_csv(props.get("valid_to")) if c in all_cols), None
    )
    validity_key = next(
        (c for c in _split_csv(props.get("validity_key")) if c in all_cols),
        None,
    )

    single_insert = (
        True
        if props.get("single_insert") is None
        else props["single_insert"].strip().lower() == "true"
    )
    bulk_insert = (
        True
        if props.get("bulk_insert") is None
        else props["bulk_insert"].strip().lower() == "true"
    )
    # Default is opt-in: only enable review workflow if explicitly set to true.
    review_required = (
        False
        if props.get("review_required") is None
        else props["review_required"].strip().lower() == "true"
    )
    return (
        not_null_cols,
        business_keys,
        not_editable,
        single_insert,
        bulk_insert,
        review_required,
        valid_from,
        valid_to,
        validity_key,
    )

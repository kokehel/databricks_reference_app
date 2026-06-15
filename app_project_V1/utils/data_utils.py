import streamlit as st
import pandas as pd
import io
import datetime

from utils.sql_utils import sql_query
from typing import Any, Dict, List, Optional


# -----------------------------------------------------------------------------
# CSV parsing (cached by file content + delimiter)
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def parse_csv_bytes(file_bytes: bytes, sep: str) -> pd.DataFrame:
    """Parse CSV from raw bytes with delimiter, cached to prevent re-parsing."""
    return pd.read_csv(
        io.BytesIO(file_bytes),
        sep=sep,
        dtype=str,
        keep_default_na=True,
        na_values=[
            "",
            "NULL",
            "null",
            "NaN",
            "nan",
            "N/A",
            "n/a",
        ],  # treat as nulls
    )


# -----------------------------------------------------------------------------
# Cached data helpers
# -----------------------------------------------------------------------------
@st.cache_data(ttl=30)
def get_data(table: str, upload_ts_col) -> pd.DataFrame:
    """Return only the latest published snapshot of the table."""
    return sql_query(
        f"""
        SELECT *
        FROM {table}
        WHERE __VERSION = (SELECT MAX(__VERSION) FROM {table})
        ORDER BY {upload_ts_col} DESC
        """
    )


@st.cache_data(ttl=30)
def get_max_key(table: str) -> int:
    """Return the highest business key that has ever been published."""
    df = sql_query(
        f"SELECT COALESCE(MAX(__KEY), 0) AS max_key FROM {table} WHERE __KEY <> 0"
    )
    if df is None or df.empty or "max_key" not in df.columns:
        return 0
    try:
        return int(pd.to_numeric(df["max_key"].iloc[0]))
    except Exception:
        return 0


@st.cache_data(ttl=300)
def get_tables(schema: str, catalog) -> List[str]:
    tables = sql_query(f"SHOW TABLES IN `{catalog}`.`{schema}`").iloc[
        :, 1
    ].tolist()
    # Defense-in-depth: internal/helper tables should not show up as user tables.
    def _is_internal_table_name(name: Any) -> bool:
        n = str(name or "").strip().lower()
        if not n:
            return True
        # App-generated helper tables
        if n.endswith("_staging") or n.endswith("_current"):
            return True
        # Backup tables (by convention these always contain `_backup`)
        if "_backup" in n:
            return True
        return False

    return [t for t in tables if not _is_internal_table_name(t)]


@st.cache_data(ttl=300)
def get_schemas(catalog: str) -> List[str]:
    """Return schemas in `catalog` that are visible to the current user 
    through Unity Catalog permissions.
    """
    df = sql_query(f"SHOW SCHEMAS IN `{catalog}`")
    if df is None or df.empty:
        return []

    # Databricks returns slightly different column names depending on context.
    # Common ones include: databaseName, schemaName, namespace.
    preferred_cols = {"databasename", "schemaname", "namespace", "name"}
    col = next(
        (c for c in df.columns if str(c).strip().lower() in preferred_cols),
        df.columns[0],
    )
    schemas = [str(x).strip() for x in df[col].tolist() if str(x).strip()]

    # Filter out system schemas that should not be user-selectable.
    blocked = {
        "information_schema",
        "app_metadata",
        "meta",
        "test",
        "testing",
    }
    schemas = [s for s in schemas if s.strip().lower() not in blocked]

    # Stable ordering for UI
    return sorted(set(schemas), key=lambda x: x.lower())


# Small helper to safely clear data cache without tripping static analyzers
def _safe_clear_data_cache() -> None:
    try:
        clear_fn = getattr(get_data, "clear", None)
        if callable(clear_fn):
            clear_fn()
    except Exception:
        pass
    try:
        clear_fn = getattr(get_max_key, "clear", None)
        if callable(clear_fn):
            clear_fn()
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Column‑type helpers
# -----------------------------------------------------------------------------


def _is_date(col: str, col_type_map: Dict) -> bool:
    dt = col_type_map.get(col, "")
    return ("timestamp" in dt) or ("date" in dt)


def _is_int(col: str, col_type_map: Dict) -> bool:
    dt = col_type_map.get(col, "").lower()
    return "int" in dt and "bigint" in dt or dt == "int" or dt.endswith("int")


def _is_float(col: str, col_type_map: Dict) -> bool:
    dt = col_type_map.get(col, "").lower()
    return (
        any(x in dt for x in ["float", "double", "decimal"])
        and "interval" not in dt
    )


def _is_bool(col: str, col_type_map: Dict) -> bool:
    dt = col_type_map.get(col, "").lower()
    return "boolean" in dt


def _to_datetime_or_none(val: Any) -> Optional[datetime.datetime]:
    """Parse timestamps robustly; return None on failure / NaT."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        # Prefer native Python types first. Pandas' datetime64 has a much
        # smaller representable range than Python's datetime (year 1..9999).
        if isinstance(val, datetime.datetime):
            return val
        if isinstance(val, datetime.date):
            return datetime.datetime.combine(val, datetime.time())

        # Fast-path ISO strings (e.g. '9999-12-31' or '9999-12-31 00:00:00').
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return None
            try:
                return datetime.datetime.fromisoformat(s)
            except Exception:
                try:
                    d = datetime.date.fromisoformat(s)
                    return datetime.datetime.combine(d, datetime.time())
                except Exception:
                    pass

        dt = pd.to_datetime(val)
        return None if pd.isna(dt) else dt.to_pydatetime()
    except Exception:
        return None


def _to_text(val: Any) -> str:
    return (
        ""
        if val is None or (isinstance(val, float) and pd.isna(val))
        else str(val)
    )


def _coerce_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in {"true", "1", "yes", "y", "t"}


# empty-value check used by validations
def _is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    if isinstance(val, str) and val.strip() == "":
        return True
    return False

import pandas as pd

from typing import List, Dict
from utils.data_utils import get_data, get_max_key
from utils.sql_utils import get_table_columns, get_table_constraints


def load_metadata(table: str, upload_ts_col):
    # -----------------------------------------------------------------------------
    # Load table & schema metadata
    # -----------------------------------------------------------------------------
    data: pd.DataFrame = get_data(table=table, upload_ts_col=upload_ts_col)
    max_key = get_max_key(table=table)

    LATEST_VERSION = (
        int(data["__VERSION"].dropna().max()) if not data.empty else 0
    )

    # DataFrame → helper dicts
    _table_cols_df = get_table_columns(
        table
    )  # columns: col_name, data_type, comment
    ALL_COLS: List[str] = _table_cols_df["col_name"].tolist()

    # get constraints from Delta properties for this table
    (
        NOT_NULL_COLS,
        BUSINESS_KEYS,
        NOT_EDITABLE_COLS,
        SINGLE_INSERT,
        BULK_INSERT,
        REVIEW_REQUIRED,
        VALID_FROM,
        VALID_TO,
        VALIDITY_KEY,
    ) = get_table_constraints(table, ALL_COLS)

    # Mapping col → lower‑case datatype string for quick lookup
    COL_TYPE_MAP: Dict[str, str] = (
        _table_cols_df.set_index("col_name")["data_type"].str.lower().to_dict()
    )

    return (
        data,
        max_key,
        ALL_COLS,
        LATEST_VERSION,
        NOT_NULL_COLS,
        BUSINESS_KEYS,
        NOT_EDITABLE_COLS,
        SINGLE_INSERT,
        BULK_INSERT,
        REVIEW_REQUIRED,
        VALID_FROM,
        VALID_TO,
        VALIDITY_KEY,
        COL_TYPE_MAP,
    )

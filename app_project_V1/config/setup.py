from typing import Any

import streamlit as st

from config.runtime import get_runtime_config


def setup_environment() -> None:
    get_runtime_config()


def setup_page_config() -> None:
    runtime_config = get_runtime_config()
    st.set_page_config(
        page_title=runtime_config.app_display_name,
        page_icon=":material/table_view:",
        layout="wide",
    )


def thousands_num_cfg(df: Any) -> dict[str, Any]:
    if df is None or df.empty:
        return {}
    ints = df.select_dtypes(include="integer").columns
    return {**{c: st.column_config.NumberColumn(c, format="%d") for c in ints}}

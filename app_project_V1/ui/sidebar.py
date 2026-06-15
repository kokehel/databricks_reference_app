import os

import streamlit as st

from utils.data_utils import _safe_clear_data_cache, get_schemas, get_tables


# -----------------------------------------------------------------------------
# Sidebar navigation
# -----------------------------------------------------------------------------
def render_sidebar(
    env: str,
    catalog: str,
    schema: str,
    app_display_name: str,
):
    st.sidebar.title(app_display_name)

    st.sidebar.caption("Runtime")
    st.sidebar.text(f"Environment: {env}")
    st.sidebar.text(f"Catalog: {catalog}")
    warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID", "Not configured")
    st.sidebar.text(f"Warehouse: {warehouse_id}")
    st.sidebar.divider()

    # Determine which schemas the signed-in user can see.
    try:
        available_schemas = get_schemas(catalog)
    except Exception:
        available_schemas = []

    if not available_schemas:
        st.sidebar.error(
            "No schemas were found for you in this catalog. "
            "Please request Unity Catalog permissions through ServiceNow for the schemas you need."
        )
        st.stop()

    # If the current schema isn't accessible, pick a sensible default.
    if schema not in available_schemas:
        schema = available_schemas[0]
        st.session_state["selected_schema"] = schema

    # Schema selection dropdown
    selected_schema = st.sidebar.selectbox(
        "Select schema",
        options=available_schemas,
        key="selected_schema",
        label_visibility="visible",
    )

    # Handle schema change: reset table selection and related state
    if "last_schema" not in st.session_state:
        st.session_state["last_schema"] = selected_schema
    if st.session_state["last_schema"] != selected_schema:
        st.session_state["last_schema"] = selected_schema
        st.session_state["selected_table"] = ""  # Reset to no table selected
        # Clear row selection / prefill
        st.session_state.pop("selected_row_for_copy", None)
        st.session_state.pop("row_selection", None)
        # Reset uploader by bumping its key
        if "uploader_version" in st.session_state:
            st.session_state["uploader_version"] += 1
        else:
            st.session_state["uploader_version"] = 1
        _safe_clear_data_cache()

    # Button-based table picker
    tables = get_tables(selected_schema, catalog)
    if (
        "selected_table" not in st.session_state
        or st.session_state.get("selected_table") not in tables
    ):
        st.session_state["selected_table"] = tables[0] if tables else ""
    if "nav_version" not in st.session_state:
        st.session_state["nav_version"] = 0

    st.sidebar.caption("Table")
    for t in tables:
        is_active = t == st.session_state.get("selected_table")
        if is_active:
            st.sidebar.button(
                f"✅ {t}",
                key=f"tblbtn_active_{t}_{st.session_state['nav_version']}",
                use_container_width=True,
                disabled=True,
            )
        else:
            if st.sidebar.button(
                t,
                key=f"tblbtn_{t}_{st.session_state['nav_version']}",
                use_container_width=True,
            ):
                st.session_state["selected_table"] = t
                st.session_state["nav_version"] += 1
                st.rerun()

    selected_table = st.session_state["selected_table"]
    table = f"`{catalog}`.`{selected_schema}`.`{selected_table}`"

    # 🔄 If user switched tables, clear row selection + reset uploader (drops any file)
    if "last_table" not in st.session_state:
        st.session_state["last_table"] = selected_table
    if st.session_state["last_table"] != selected_table:
        st.session_state["last_table"] = selected_table
        # clear row selection / prefill
        st.session_state.pop("selected_row_for_copy", None)
        st.session_state.pop("row_selection", None)
        # reset uploader by bumping its key
        if "uploader_version" in st.session_state:
            st.session_state["uploader_version"] += 1
        else:
            st.session_state["uploader_version"] = 1
        _safe_clear_data_cache()

    return table, selected_table

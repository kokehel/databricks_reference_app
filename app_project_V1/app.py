"""
Main Streamlit application for browsing and editing reference-data tables.
"""

from __future__ import annotations

from contextlib import suppress

import streamlit as st

from config.constants import (
    AUDIT_COLS,
    KEY_COL,
    UPLOAD_FILE_NAME_COL,
    UPLOAD_TS_COL,
    UPLOAD_USER_COL,
    UPLOAD_VERSION_COL,
    get_selected_schema,
)
from config.metadata import load_metadata
from config.runtime import get_runtime_config
from config.setup import setup_environment, setup_page_config
from styles.styles import inject_global_styles
from ui.actions import render_actions
from ui.data_viewer import inline_data_viewer
from ui.hero import render_hero
from ui.review_panel import render_review_panel
from ui.sidebar import render_sidebar
from utils.review_utils import ensure_meta_objects

# -----------------------------------------------------------------------------
# Setup streamlit page config, environment & styles
# -----------------------------------------------------------------------------
setup_page_config()
runtime_config = get_runtime_config()

# Apply styles early
inject_global_styles()

setup_environment()

if not runtime_config.warehouse_id:
    st.error(
        "DATABRICKS_WAREHOUSE_ID is not configured. "
        "Set it in Databricks Apps or the Azure DevOps variable group for this deployment."
    )
    st.stop()

ENV = runtime_config.environment
CATALOG = runtime_config.catalog

# -----------------------------------------------------------------------------
# Initialize review/approval system metadata (creates schema/table if needed)
# -----------------------------------------------------------------------------
with suppress(Exception):
    ensure_meta_objects(CATALOG)

# -----------------------------------------------------------------------------
# Get selected schema, tables and metadata
# -----------------------------------------------------------------------------
SCHEMA = get_selected_schema(runtime_config.default_schema)

TABLE, selected_table = render_sidebar(
    env=ENV,
    catalog=CATALOG,
    schema=SCHEMA,
    app_display_name=runtime_config.app_display_name,
)

(
    data,
    MAX_KEY,
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
) = load_metadata(table=TABLE, upload_ts_col=UPLOAD_TS_COL)

# -----------------------------------------------------------------------------
# Prefill token: ensures widgets refresh when a new row is loaded
# -----------------------------------------------------------------------------
if "prefill_token" not in st.session_state:
    st.session_state.prefill_token = 0  # integer counter

# -----------------------------------------------------------------------------
# Navigation: Data Entry vs Review & Approve
# -----------------------------------------------------------------------------
if "page_mode" not in st.session_state:
    st.session_state.page_mode = "data_entry"

page_tabs = (
    st.tabs(["📝 Data Entry", "📋 Review & Approve"])
    if REVIEW_REQUIRED
    else st.tabs(["📝 Data Entry"])
)

# -----------------------------------------------------------------------------
# Data Entry Tab
# -----------------------------------------------------------------------------
with page_tabs[0]:
    # Branded hero
    render_hero(
        title=selected_table,
        eyebrow=runtime_config.app_display_name,
        logo_path=runtime_config.logo_path,
    )

    # -----------------------------------------------------------------------------
    # Setup inline data viewer and render user actions
    # -----------------------------------------------------------------------------
    latest, displayed_latest, event = inline_data_viewer(
        data=data, all_cols=ALL_COLS
    )

    render_actions(
        latest=latest,
        displayed_latest=displayed_latest,
        selected_table=selected_table,
        single_insert=SINGLE_INSERT,
        bulk_insert=BULK_INSERT,
        review_required=REVIEW_REQUIRED,
        event=event,
        table=TABLE,
        max_key=MAX_KEY,
        key_col=KEY_COL,
        latest_version=LATEST_VERSION,
        upload_ts_col=UPLOAD_TS_COL,
        upload_version_col=UPLOAD_VERSION_COL,
        upload_user_col=UPLOAD_USER_COL,
        upload_file_name_col=UPLOAD_FILE_NAME_COL,
        all_cols=ALL_COLS,
        audit_cols=AUDIT_COLS,
        not_editable_cols=NOT_EDITABLE_COLS,
        col_type_map=COL_TYPE_MAP,
        not_null_cols=NOT_NULL_COLS,
        business_keys=BUSINESS_KEYS,
        valid_from=VALID_FROM,
        valid_to=VALID_TO,
        validity_key=VALIDITY_KEY,
        catalog=CATALOG,
    )

# -----------------------------------------------------------------------------
# Review & Approve Tab
# -----------------------------------------------------------------------------
if REVIEW_REQUIRED:
    with page_tabs[1]:
        render_review_panel(catalog=CATALOG, target_table=TABLE)


st.markdown("</div>", unsafe_allow_html=True)

import streamlit as st


# Initialize selected schema in session state if not present
def get_selected_schema(default_schema: str) -> str:
    if "selected_schema" not in st.session_state:
        st.session_state["selected_schema"] = default_schema

    return st.session_state["selected_schema"]


# audit columns added automatically on insert
KEY_COL = "__KEY"  # primary key column, auto-generated
UPLOAD_TS_COL = "__UPLOAD_TIMESTAMP"
UPLOAD_VERSION_COL = "__VERSION"
VERSION_TS_COL = "__VERSION_TIMESTAMP"  # timestamp of when this version/snapshot was published
UPLOAD_USER_COL = "__UPLOADED_BY"
UPLOAD_FILE_NAME_COL = "__UPLOAD_FILE_NAME"

# List of all audit columns for consistent reference
AUDIT_COLS = [
    KEY_COL,
    UPLOAD_TS_COL,
    UPLOAD_VERSION_COL,
    VERSION_TS_COL,
    UPLOAD_USER_COL,
    UPLOAD_FILE_NAME_COL,
]

# Change Request (CR) related constants
CR_ID_COL = "__CR_ID"  # Change request ID column in staging tables
CR_STATUS_PENDING = "pending"
CR_STATUS_APPROVED = "approved"
CR_STATUS_REJECTED = "rejected"
CR_STATUS_CANCELLED = "cancelled"

# Metadata schema and table for change requests
META_SCHEMA_NAME = "app_metadata"
META_CR_TABLE_NAME = "change_requests"

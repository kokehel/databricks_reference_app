import hashlib
import streamlit as st
import pandas as pd
import datetime
import time

from config.setup import thousands_num_cfg
from typing import Any, Dict, List, Optional
from utils.data_utils import (
    parse_csv_bytes,
    _coerce_bool,
    _is_bool,
    _is_date,
    _is_float,
    _is_int,
    _to_datetime_or_none,
    _to_text,
    _safe_clear_data_cache,
)
from utils.sql_utils import (
    bulk_insert_data,
    clean_df,
    get_current_user,
    get_current_timestamp,
    get_table_schema,
    sql_query,
    validate_df,
)
from utils.review_utils import create_change_request
from utils.validation_utils import (
    validate_business_key_uniqueness,
    validate_date_range_constraints,
    validate_single_row_types,
    inject_audit_columns,
    get_next_version,
)
from config.constants import VERSION_TS_COL


def date_range_constraint(data, validity_key, start_date, end_date):
    """
    Returns list of conflicting IDs and overlapping rows.
    """

    df = data.copy()

    df[start_date] = pd.to_datetime(df[start_date], errors="coerce")
    df[end_date] = pd.to_datetime(df[end_date], errors="coerce")
    df[end_date] = df[end_date].fillna(pd.Timestamp("2100-12-31"))

    df = df.sort_values([validity_key, start_date]).reset_index(drop=True)

    conflicts = []

    for id_, group in df.groupby(validity_key):
        prev_end = None
        prev_row = None
        for _, row in group.iterrows():
            if prev_end and row[start_date] <= prev_end:
                conflicts.append([row, prev_row])
            prev_end = (
                max(prev_end, row[end_date]) if prev_end else row[end_date]
            )
            prev_row = row

    return conflicts


def download_latest_version_as_csv(latest: str, selected_table: str):
    # -----------------------------------------------------------------------------
    # Download latest version as CSV
    # -----------------------------------------------------------------------------
    if not latest.empty:
        latest_no_key = latest.copy()
        latest_no_key.pop("__KEY")
        csv = latest_no_key.to_csv(index=False, sep=";").encode("utf-8")

        st.download_button(
            label="📥  Download latest version as CSV",
            data=csv,
            file_name=f"{selected_table}_version_{latest_no_key['__VERSION'].iloc[0]}.csv",
            mime="text/csv",
        )


def single_insert_actions(
    single_insert,
    review_required,
    event,
    latest,
    displayed_latest,
    table,
    max_key,
    key_col,
    latest_version,
    upload_ts_col,
    upload_version_col,
    upload_user_col,
    upload_file_name_col,
    all_cols,
    audit_cols,
    not_editable_cols,
    col_type_map,
    not_null_cols,
    business_keys,
    valid_from,
    valid_to,
    validity_key,
    catalog,
):
    if single_insert:
        # -----------------------------------------------------------------------------
        # Clear row selection
        # -----------------------------------------------------------------------------

        if st.button("🧹 Clear row selection", key="btn_clear_sel"):
            st.session_state.pop("selected_row_for_copy", None)
            st.session_state.pop("row_selection", None)
            st.session_state.prefill_token += 1
            st.rerun()

        # -----------------------------------------------------------------------------
        # Selected row handling
        # -----------------------------------------------------------------------------

        def _get_selected_row_idxs(evt, source_df: pd.DataFrame) -> List[int]:
            """Return all selected row indices, robust to different event/session shapes."""

            def _normalize_rows(obj: Any) -> List[int]:
                # Resolve callables
                try:
                    if callable(obj):
                        obj = obj()
                except Exception:
                    return []
                # Dict form {"rows": [...]} or nested under selection
                if isinstance(obj, dict):
                    if "selection" in obj:
                        return _normalize_rows(
                            obj.get("selection", {}).get("rows")
                        )
                    return _normalize_rows(obj.get("rows"))
                # Attribute form .rows
                if hasattr(obj, "rows"):
                    return _normalize_rows(getattr(obj, "rows"))
                # Already a sequence of indices
                try:
                    seq = list(obj) if obj is not None else []
                except Exception:
                    return []
                out: List[int] = []
                for x in seq:
                    try:
                        ix = int(x)
                        if 0 <= ix < len(source_df):
                            out.append(ix)
                    except Exception:
                        continue
                return sorted(set(out))

            # st.dataframe no longer returns an event; keep for backward compat
            sel = getattr(evt, "selection", None)
            rows = _normalize_rows(sel)
            if not rows:
                ss = st.session_state.get("row_selection", {})
                if isinstance(ss, dict):
                    rows = _normalize_rows(ss.get("rows"))
            return rows

        selected_idxs: List[int] = _get_selected_row_idxs(event, displayed_latest)
        selected_idx: Optional[int] = (
            selected_idxs[0] if selected_idxs else None
        )

        # -----------------------------------------------------------------------------
        # Load‑into‑form / Delete buttons
        # -----------------------------------------------------------------------------
        if selected_idxs and not latest.empty:
            sel_keys = displayed_latest.iloc[selected_idxs][key_col].tolist()
            st.caption(
                f"{len(selected_idxs):,} row(s) selected. Keys: "
                + ", ".join(map(str, sel_keys[:5]))
                + (" …" if len(sel_keys) > 5 else "")
            )

            btn_cols = st.columns([1, 1, 2])
            with btn_cols[0]:
                label = (
                    "📥 Load selected row into form"
                    if len(selected_idxs) == 1
                    else "📥 Load first selected row into form"
                )
                if st.button(label, key="btn_load_row"):
                    with st.spinner("Loading row into form…"):
                        st.session_state.selected_row_for_copy = displayed_latest.iloc[
                            selected_idx
                        ].to_dict()  # first
                        st.session_state.prefill_token += (
                            1  # bump so widgets get fresh keys
                        )
                        st.rerun()

            with btn_cols[1]:
                # Delete selected rows by publishing a full new version without these keys
                can_delete = not latest.empty
                if st.button(
                    f"🗑️ Delete selected ({len(selected_idxs)})",
                    key="btn_delete_rows",
                    disabled=not can_delete,
                ):
                    if latest.empty:
                        st.warning("Nothing to delete.")
                    else:
                        next_version = (latest_version or 0) + 1
                        version_ts = get_current_timestamp()
                        actor = get_current_user()
                        keys_to_delete = set(sel_keys)
                        new_df = latest[
                            ~latest[key_col].isin(keys_to_delete)
                        ].copy()

                        # If table becomes empty: publish an "empty snapshot" marker row.
                        # We reserve __KEY == 0 for this internal marker and hide it in the UI.
                        became_empty = new_df.empty
                        if became_empty:
                            st.warning(
                                "⚠️ This deletion results in an **empty table snapshot**. "
                                "We will publish a new empty version."
                            )

                            # Build a single marker row so __VERSION advances
                            # (bulk_insert_data is a no-op on empty DF).
                            marker: Dict[str, Any] = {c: None for c in all_cols}
                            marker[key_col] = 0  # reserved marker key

                            # Fill required (not-null) non-audit columns with safe defaults.
                            for c in not_null_cols:
                                if c in audit_cols or c == key_col:
                                    continue
                                if c not in marker:
                                    continue
                                if marker[c] is not None:
                                    continue
                                try:
                                    if _is_bool(col=c, col_type_map=col_type_map):
                                        marker[c] = False
                                    elif _is_int(col=c, col_type_map=col_type_map):
                                        marker[c] = 0
                                    elif _is_float(col=c, col_type_map=col_type_map):
                                        marker[c] = 0.0
                                    elif _is_date(col=c, col_type_map=col_type_map):
                                        marker[c] = datetime.date(1900, 1, 1)
                                    else:
                                        marker[c] = "__EMPTY_SNAPSHOT__"
                                except Exception:
                                    marker[c] = "__EMPTY_SNAPSHOT__"

                            new_df = pd.DataFrame([marker])

                        # Version-level audit: update version + version timestamp across the snapshot
                        new_df[upload_version_col] = next_version
                        if VERSION_TS_COL in all_cols:
                            new_df[VERSION_TS_COL] = version_ts

                        # Row-level audit: only touch row audit columns for the marker row (if any).
                        if became_empty:
                            new_df[upload_ts_col] = version_ts
                            new_df[upload_user_col] = actor
                            new_df[upload_file_name_col] = "ui-delete-empty-snapshot"
                        # Ensure column order matches the target table schema
                        new_df = new_df.reindex(columns=all_cols)

                        with st.spinner(
                            "Publishing new version without the selected rows…"
                        ):
                            bulk_insert_data(table, pd.DataFrame(new_df))
                            visible_rows = 0 if became_empty else len(new_df)
                            st.success(
                                f"Published version {next_version} with {visible_rows:,} rows "
                                f"(deleted {len(keys_to_delete):,} row(s))."
                            )
                            # clear selection, refresh
                            st.session_state.pop(
                                "selected_row_for_copy", None
                            )
                            st.session_state.pop("row_selection", None)
                            _safe_clear_data_cache()
                            st.rerun()
        else:
            st.caption("No row selected.")

        loaded_row: Dict[str, Any] = st.session_state.get(
            "selected_row_for_copy", {}
        )

        # -----------------------------------------------------------------------------
        # Add / Edit Row form (prefill‑aware)
        # -----------------------------------------------------------------------------
        st.markdown("<div class='app-card'>", unsafe_allow_html=True)
        st.subheader("Add / Edit Row")
        st.info(
            "**Updating a row:** Select the row from the table above first and press *Load selected row into form*.\n\n"
            "**Adding a new row:** Make sure **no** row is selected or press *Clear row selection*."
        )

        prefill_token = st.session_state.prefill_token  # stable within this run

        for col in all_cols:
            widget_key = f"new_{col}_{prefill_token}"
            if col not in not_null_cols and col not in audit_cols and col not in not_editable_cols and _is_int(col=col, col_type_map=col_type_map):
                null_value = st.checkbox(f"No value for {col}", key=f"{widget_key}_null")
            


        # Make inputs *sticky* across reruns so a click elsewhere doesn't wipe your edits
        with st.form("add_row_form", clear_on_submit=False):
            new_row: Dict[str, Any] = {}

            # Dynamic button label makes intent clearer
            submit_label = "Save Changes" if loaded_row else "Add Row"

            # Field widgets per column type
            for col in all_cols:
                if col in audit_cols or col in not_editable_cols:
                    continue  # auto fields

                widget_key = f"new_{col}_{prefill_token}"
                raw_val = loaded_row.get(col)

                if _is_bool(col=col, col_type_map=col_type_map):
                    bool_val = (
                        _coerce_bool(raw_val) if raw_val is not None else False
                    )
                    new_row[col] = st.checkbox(
                        col, value=bool_val, key=widget_key
                    )

                elif _is_int(col=col, col_type_map=col_type_map):
                    try:
                        int_val = (
                            int(raw_val)
                            if raw_val
                            not in (
                                None,
                                "",
                            )
                            else 0
                        )
                    except Exception:
                        int_val = 0
                        
                    is_null = st.session_state.get(f"{widget_key}_null", False)
                    if is_null:
                        new_row[col] = None
                    else:
                        new_row[col] = st.number_input(
                            f"Enter value for {col}",
                            value=int_val,
                            step=1,
                            key=widget_key
                        )

                elif _is_float(col=col, col_type_map=col_type_map):
                    try:
                        f_val = (
                            float(str(raw_val).replace(",", "."))
                            if raw_val
                            not in (
                                None,
                                "",
                            )
                            else 0.0
                        )
                    except Exception:
                        f_val = 0.0
                    new_row[col] = st.number_input(
                        f"Enter value for {col}", value=f_val, key=widget_key
                    )

                elif _is_date(col=col, col_type_map=col_type_map):
                    parsed_dt = _to_datetime_or_none(raw_val)
                    dt_val = (
                        parsed_dt.date()
                        if isinstance(parsed_dt, datetime.datetime)
                        else parsed_dt
                    )
                    if dt_val is None:
                        dt_val = datetime.date.today()

                    new_row[col] = st.date_input(
                        col,
                        value=dt_val,
                        max_value=datetime.date(9999, 12, 31),
                        key=widget_key,
                    )

                else:  # text / fallback
                    new_row[col] = st.text_input(
                        f"Enter value for {col}",
                        value=_to_text(raw_val),
                        key=widget_key,
                    )

            # Add comment field for change request
            comment = ""
            if review_required:
                comment = st.text_area(
                    "Comment (optional)",
                    key=f"comment_{prefill_token}",
                    help="Add a note about this change for reviewers",
                )

            submitted = st.form_submit_button(submit_label, type="primary")

            if submitted:
                # Preserve non-editable columns on updates
                if loaded_row:
                    for c in not_editable_cols:
                        if c in audit_cols:
                            continue
                        if c == key_col:
                            continue
                        if c not in new_row:
                            new_row[c] = loaded_row.get(c)

                # primary key
                if loaded_row:
                    new_row[key_col] = loaded_row.get(key_col)
                else:
                    new_row[key_col] = int(max_key) + 1 if int(max_key) > 0 else 1
                action_label = "update" if loaded_row else "add"

                # normalise date widgets → datetime
                for col in all_cols:
                    if col in audit_cols or col in not_editable_cols:
                        continue
                    if (
                        _is_date(col=col, col_type_map=col_type_map)
                        and isinstance(new_row[col], datetime.date)
                        and not isinstance(new_row[col], datetime.datetime)
                    ):
                        new_row[col] = datetime.datetime.combine(
                            new_row[col], datetime.time()
                        )

                # Validate types and show Streamlit errors if needed
                errors = validate_single_row_types(
                    row=new_row,
                    audit_cols=audit_cols,
                    not_editable_cols=not_editable_cols,
                    not_null_cols=not_null_cols,
                    col_type_map=col_type_map,
                )

                # Uniqueness check for business keys against latest snapshot
                if not errors and business_keys:
                    df_check = (
                        latest.copy()
                        if not latest.empty
                        else pd.DataFrame(columns=all_cols)
                    )
                    exclude_key = new_row.get(key_col) if loaded_row else None
                    
                    new_row_df = pd.DataFrame([new_row])
                    bk_errors = validate_business_key_uniqueness(
                        new_data=new_row_df,
                        existing_data=df_check,
                        business_keys=business_keys,
                        key_col=key_col,
                        col_type_map=col_type_map,
                        exclude_key=exclude_key,
                    )
                    errors.extend(bk_errors)

                # Check if there are overlapping valid records
                if not errors and validity_key:
                    df_check = (
                        latest.copy()
                        if not latest.empty
                        else pd.DataFrame(columns=all_cols)
                    )
                    exclude_key = new_row.get(key_col) if loaded_row else None
                    
                    new_row_df = pd.DataFrame([new_row])
                    date_errors = validate_date_range_constraints(
                        new_data=new_row_df,
                        existing_data=df_check,
                        validity_key=validity_key,
                        valid_from=valid_from,
                        valid_to=valid_to,
                        key_col=key_col,
                        all_cols=all_cols,
                        exclude_key=exclude_key,
                        date_range_constraint_func=date_range_constraint,
                    )
                    errors.extend(date_errors)

                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    try:
                        # Build a full new snapshot so the version advances on every change.
                        # This is important for reference data tables where the UI shows the latest version.
                        base_df = (
                            latest.copy()
                            if latest is not None and not latest.empty
                            else pd.DataFrame(columns=all_cols)
                        )
                        if loaded_row:
                            # Remove the old row on update
                            base_df = base_df[base_df[key_col] != new_row[key_col]]

                        new_row_df = pd.DataFrame([new_row])

                        next_version = get_next_version(table, upload_version_col)

                        # --- Audit strategy ---
                        # Row-level audit (upload_ts/user/file) should only be updated for the row being added/edited.
                        # Version-level audit (version + version timestamp) applies to all rows in the snapshot.
                        version_ts = get_current_timestamp()
                        actor = get_current_user()

                        # Stamp version-level audit on the carried-forward rows without overwriting their row-level audit.
                        if not base_df.empty:
                            base_df[upload_version_col] = next_version
                            if VERSION_TS_COL in all_cols:
                                base_df[VERSION_TS_COL] = version_ts

                        # Stamp row-level + version-level audit on the new/edited row
                        new_row_df[upload_ts_col] = version_ts
                        new_row_df[upload_user_col] = actor
                        new_row_df[upload_file_name_col] = f"ui-single-{action_label}"
                        new_row_df[upload_version_col] = next_version
                        if VERSION_TS_COL in all_cols:
                            new_row_df[VERSION_TS_COL] = version_ts

                        new_df = pd.concat([base_df, new_row_df], ignore_index=True)
                        # Reorder columns to match table schema (also ensures we include all expected columns)
                        new_df = new_df.reindex(columns=all_cols)

                        if review_required:
                            with st.spinner("Submitting change request…"):
                                current_user = get_current_user()
                                cr_id = create_change_request(
                                    catalog=catalog,
                                    target_table=table,
                                    submitted_by=current_user,
                                    change_type=f"single_{action_label}",
                                    note=comment or "",
                                    rows_df=new_df,
                                )
                            st.session_state.last_cr_id = cr_id
                            st.session_state.success_message = (
                                f"✅ Change request {cr_id} submitted successfully! "
                                f"It is now pending review and approval."
                            )
                        else:
                            with st.spinner("Publishing new version…"):
                                bulk_insert_data(table, new_df)
                            st.session_state.success_message = (
                                f"✅ Published version {next_version} successfully."
                            )

                        # Clear selection/prefill only on success
                        st.session_state.pop(
                            "selected_row_for_copy", None
                        )  # forget the prefill
                        st.session_state.pop(
                            "row_selection", None
                        )  # forget the table highlight
                        st.session_state.prefill_token += (
                            1  # new keys for widgets
                        )
                        st.session_state.show_success = True  # flag for banner
                        _safe_clear_data_cache()
                        st.rerun()
                    except Exception as exc:
                        if review_required:
                            st.error(f"Error submitting change request: {exc}")
                        else:
                            st.error(f"Error publishing new version: {exc}")

        # Show success message if flag is set
        if st.session_state.get("show_success", False):
            msg = st.session_state.get("success_message", "")
            if msg:
                st.success(msg)
            st.session_state.show_success = False
            st.session_state.pop("last_cr_id", None)
            st.session_state.pop("success_message", None)


def bulk_actions(
    bulk_insert,
    review_required,
    table,
    selected_table,
    upload_ts_col,
    all_cols,
    audit_cols,
    not_null_cols,
    business_keys,
    upload_version_col,
    upload_user_col,
    upload_file_name_col,
    valid_from,
    valid_to,
    validity_key,
    catalog,
):
    # -----------------------------------------------------------------------------
    # Bulk CSV append section
    # -----------------------------------------------------------------------------
    if not bulk_insert:
        st.stop()

    if "uploader_version" not in st.session_state:
        st.session_state["uploader_version"] = 0  # initialise once

    def new_uploader_key() -> str:
        return f"csv_file_{st.session_state['uploader_version']}"

    st.divider()
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.header("Bulk CSV Upload")
    st.subheader(
        "Only upload complete snapshots"
    )
    st.info("Upload preview is **limited** to 100 rows.")
    st.info(
        "If you see any unsuspected errors try switching **CSV delimiters**."
    )

    # When switching tables we bump the uploader key above → any selected file disappears
    delim = st.radio(
        "Choose CSV delimiter",
        options=[";", ","],
        format_func=lambda x: ", (comma)" if x == "," else "; (semicolon)",
        horizontal=True,
    )
    file_obj = st.file_uploader(
        "Upload CSV file",
        type=["csv"],
        key=new_uploader_key(),  # changing this resets the control → drops file
    )

    if file_obj is not None:
        preview_status = st.status(
            "Validating upload…",
            expanded=True,
        )
        preview_progress = st.progress(0)

        def _update_preview_progress(value: int) -> None:
            preview_progress.progress(value)
            preview_status.update(
                label="Validating upload…",
                state="running",
                expanded=True,
            )

        def _fail_preview() -> None:
            preview_status.update(
                label="Upload preview failed",
                state="error",
                expanded=True,
            )

        file_sig = "nofile"
        try:
            _update_preview_progress(10)
            # Read once as bytes and parse via cached helper to avoid oscillations
            # in widget renders that can happen when re-reading file handles.
            _raw = file_obj.getvalue()
            df_upload = parse_csv_bytes(_raw, delim)
            file_sig = hashlib.md5(_raw + delim.encode()).hexdigest()[:10]

            # Replace spaces in column names with underscores
            df_upload.columns = [
                col.replace(" ", "_").lower() if col not in audit_cols else col
                for col in df_upload.columns
            ]

            # Show CSV row count and last full upload comparison
            csv_row_count = len(df_upload)
            st.info(f"CSV contains **{csv_row_count:,}** rows")

            # Count rows for the latest full set
            _update_preview_progress(20)
            last_query = f"""
            SELECT COUNT(*) AS row_count
            FROM (
            SELECT ROW_NUMBER() OVER (PARTITION BY __KEY ORDER BY {upload_ts_col} DESC) AS rn
            FROM {table}
            WHERE __VERSION = (SELECT MAX(__VERSION) FROM {table})
              AND __KEY <> 0  -- ignore empty-snapshot marker rows
            ) t
            WHERE rn = 1;
            """
            try:
                last_full_result = sql_query(last_query)
                row_count_val = 0
                if (
                    not last_full_result.empty
                    and "row_count" in last_full_result.columns
                ):
                    # Extract a scalar safely
                    row_count_val = int(
                        pd.to_numeric(last_full_result["row_count"].iloc[0])
                    )
                if row_count_val > 0:
                    last_full_count = row_count_val
                    st.info(
                        f"Last full upload contained **{last_full_count:,}** rows"
                    )

                    diff = csv_row_count - last_full_count
                    if diff > 0:
                        st.success(
                            f"📈 CSV has **{diff:,}** more rows than last full upload"
                        )
                    elif diff < 0:
                        st.warning(
                            f"📉 CSV has **{abs(diff):,}** fewer rows than last full upload"
                        )
                    else:
                        st.info(
                            "📊 CSV has the same number of rows as last full upload"
                        )
                else:
                    st.info("No previous full uploads found for comparison")
            except Exception:
                st.info("Could not retrieve last full upload count")

        except Exception as exc:
            _fail_preview()
            st.error(f"Could not read CSV: {exc}")
            df_upload = pd.DataFrame()

        if not df_upload.empty:
            # Render preview; Streamlit's container() doesn't accept key, so we use
            # a placeholder and then populate it.
            preview_placeholder = st.empty()
            with preview_placeholder.container():
                _update_preview_progress(30)
                # ensure required columns present (excluding audit cols)
                required_cols = [c for c in all_cols if c not in audit_cols]
                missing = [
                    c for c in required_cols if c not in df_upload.columns
                ]
                if missing:
                    _fail_preview()
                    st.error(
                        "Missing required column(s): " + ", ".join(missing)
                    )
                    st.stop()

                # check for extra columns not in the table schema
                expected_cols = set(required_cols)
                actual_cols = set(df_upload.columns)
                extra_cols = [c for c in actual_cols if c not in expected_cols]
                if extra_cols:
                    st.warning(
                        "Extra column(s) found (will be ignored): "
                        + ", ".join(extra_cols)
                    )
                    # throw out the extra columns
                    df_upload = df_upload.drop(columns=extra_cols)

                schema = get_table_schema(table)

                # Filter out audit columns from schema for cleaning/validation
                filtered_schema = {
                    col: dtype
                    for col, dtype in schema.items()
                    if col not in audit_cols
                }

                _update_preview_progress(45)
                df_fixed, fixes = clean_df(df_upload, filtered_schema)

                _update_preview_progress(55)
                issues = validate_df(df_fixed, filtered_schema)

                # 1️⃣ Banner with auto-fix report
                if fixes:
                    st.info(
                        "🔧 Auto-fixed values in column(s): "
                        + ", ".join(
                            f"In column: {col} fixed {n} rows"
                            for col, n in fixes.items()
                        )
                    )

                # 2️⃣ If anything still wrong → block insert
                if issues:
                    _fail_preview()
                    st.error(
                        f"⛔ Found {sum(len(v) for v in issues.values())} unfixable cells. Click see details to inspect."
                    )
                    with st.expander("See details"):
                        st.write(issues)
                    st.stop()

                # enforce not-null and uniqueness constraints on the cleaned CSV
                # 1) Required (not-null) checks
                _update_preview_progress(65)
                if not_null_cols:
                    missing_required: Dict[str, int] = {}
                    for col in [
                        c for c in not_null_cols if c in df_fixed.columns
                    ]:
                        m = df_fixed[col].isna() | (
                            df_fixed[col].astype(str).str.strip() == ""
                        )
                        cnt = int(m.sum())
                        if cnt > 0:
                            missing_required[col] = cnt
                    if missing_required:
                        st.error(
                            "⛔ Required columns contain empty values: "
                            + ", ".join(
                                f"{c} ({n})"
                                for c, n in missing_required.items()
                            )
                        )
                        with st.expander(
                            "See sample row indices with missing required values"
                        ):
                            details = {
                                c: df_fixed.index[
                                    df_fixed[c].isna()
                                    | (
                                        df_fixed[c].astype(str).str.strip()
                                        == ""
                                    )
                                ].tolist()[:200]
                                for c in missing_required
                            }
                            st.write(details)
                        _fail_preview()
                        st.stop()

                # 2) Business key uniqueness within the file (new snapshot must be unique)
                _update_preview_progress(78)
                if business_keys:
                    # Confirm BK columns exist in upload
                    missing_bk_cols = [
                        c for c in business_keys if c not in df_fixed.columns
                    ]
                    if missing_bk_cols:
                        _fail_preview()
                        st.error(
                            "⛔ CSV missing business key columns: "
                            + ", ".join(missing_bk_cols)
                        )
                        st.stop()

                    non_null_subset = df_fixed.dropna(subset=business_keys)
                    # remove rows with empty-string BKs from duplicate check
                    nn_mask = non_null_subset[business_keys].applymap(
                        lambda x: str(x).strip() != ""
                    )
                    non_null_subset = non_null_subset[nn_mask.all(axis=1)]

                    if not non_null_subset.empty:
                        dup_counts = non_null_subset.groupby(
                            business_keys, dropna=False
                        ).size()
                        dups = dup_counts[dup_counts > 1]
                        if not dups.empty:
                            st.error(
                                f"⛔ Duplicate business key values found in CSV for "
                                f"{', '.join(business_keys)}. Please ensure uniqueness within the file."
                            )
                            with st.expander(
                                "See duplicate key values (top 100)"
                            ):
                                st.dataframe(
                                    dups.reset_index()
                                    .rename(columns={0: "count"})
                                    .head(100),
                                    use_container_width=True,
                                )
                            _fail_preview()
                            st.stop()

                _update_preview_progress(90)
                if validity_key:
                    conflicts = []
                    conflicts = date_range_constraint(
                        data=df_fixed,
                        validity_key=validity_key,
                        start_date=valid_from,
                        end_date=valid_to,
                    )

                    if conflicts:
                        conflict_keys = set([
                            str(row.at[validity_key])
                            for conflict in conflicts
                            for row in conflict
                        ])
                        st.error(
                            f"⛔ Overlapping valid records found in CSV for {validity_key} "
                            f"{conflict_keys}. Please ensure uniqueness within the file."
                        )
                        _fail_preview()
                        st.stop()

                # Get next version and add auto-generated key column
                _update_preview_progress(97)
                next_version = get_next_version(table, upload_version_col)
                df_fixed.insert(0, "__KEY", range(1, len(df_upload) + 1))

                # Inject audit cols
                df_fixed = inject_audit_columns(
                    df=df_fixed,
                    upload_ts_col=upload_ts_col,
                    upload_version_col=upload_version_col,
                    upload_user_col=upload_user_col,
                    upload_file_name_col=upload_file_name_col,
                    latest_version=next_version,
                    file_name=file_obj.name,
                )
                # Version-level timestamp (if the table has this column)
                if VERSION_TS_COL in all_cols:
                    df_fixed[VERSION_TS_COL] = get_current_timestamp()
                # reorder to match prod
                df_fixed = df_fixed[
                    [c for c in all_cols if c in df_fixed.columns]
                ]

                preview_progress.progress(100)
                preview_status.update(
                    label="Upload preview ready",
                    state="complete",
                    expanded=False,
                )

                with st.form(f"append_confirm_{file_sig}"):
                    st.dataframe(
                        df_fixed.head(100),
                        use_container_width=True,
                        column_config=thousands_num_cfg(df_fixed),
                    )
                    bulk_comment = ""
                    if review_required:
                        # Add comment field for bulk upload
                        bulk_comment = st.text_area(
                            "Comment (optional)",
                            key=f"bulk_comment_{file_sig}",
                            help="Add a note about this bulk upload for reviewers",
                        )
                    confirm = st.form_submit_button(
                        "Submit for Review" if review_required else "Insert now"
                    )
                if confirm:
                    if review_required:
                        with st.spinner("Submitting change request…"):
                            # Create change request instead of direct insert
                            current_user = get_current_user()
                            cr_id = create_change_request(
                                catalog=catalog,
                                target_table=table,
                                submitted_by=current_user,
                                change_type="bulk",
                                note=bulk_comment or "",
                                rows_df=df_fixed,
                            )
                        msg = (
                            f"✅ Change request {cr_id} submitted! {len(df_fixed):,} rows are now pending review and approval."
                        )
                    else:
                        with st.spinner("Inserting rows…"):
                            bulk_insert_data(table, df_fixed)
                        msg = f"✅ Inserted {len(df_fixed):,} rows successfully."
                    placeholder = st.empty()
                    placeholder.success(msg)
                    time.sleep(3)
                    st.session_state["uploader_version"] += (
                        1  # reset uploader → drops selected file
                    )
                    _safe_clear_data_cache()
                    st.rerun()


def render_actions(
    latest: str,
    displayed_latest,
    selected_table: str,
    single_insert,
    bulk_insert,
    review_required,
    event,
    table,
    max_key,
    key_col,
    latest_version,
    upload_ts_col,
    upload_version_col,
    upload_user_col,
    upload_file_name_col,
    all_cols,
    audit_cols,
    not_editable_cols,
    col_type_map,
    not_null_cols,
    business_keys,
    valid_from,
    valid_to,
    validity_key,
    catalog,
):
    download_latest_version_as_csv(latest=latest, selected_table=selected_table)
    single_insert_actions(
        latest=latest,
        displayed_latest=displayed_latest,
        single_insert=single_insert,
        review_required=review_required,
        event=event,
        table=table,
        max_key=max_key,
        key_col=key_col,
        latest_version=latest_version,
        upload_ts_col=upload_ts_col,
        upload_version_col=upload_version_col,
        upload_user_col=upload_user_col,
        upload_file_name_col=upload_file_name_col,
        all_cols=all_cols,
        audit_cols=audit_cols,
        not_editable_cols=not_editable_cols,
        col_type_map=col_type_map,
        not_null_cols=not_null_cols,
        business_keys=business_keys,
        valid_from=valid_from,
        valid_to=valid_to,
        validity_key=validity_key,
        catalog=catalog,
    )
    bulk_actions(
        bulk_insert=bulk_insert,
        review_required=review_required,
        table=table,
        selected_table=selected_table,
        upload_ts_col=upload_ts_col,
        all_cols=all_cols,
        audit_cols=audit_cols,
        not_null_cols=not_null_cols,
        business_keys=business_keys,
        upload_version_col=upload_version_col,
        upload_user_col=upload_user_col,
        upload_file_name_col=upload_file_name_col,
        valid_from=valid_from,
        valid_to=valid_to,
        validity_key=validity_key,
        catalog=catalog,
    )

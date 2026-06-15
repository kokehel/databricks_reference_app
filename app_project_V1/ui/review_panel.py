"""
Review and approval panel for change requests.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from typing import Optional

from utils.review_utils import (
    get_change_requests,
    get_staging_rows,
    approve_change_request,
    reject_change_request,
    get_unique_tables,
    get_unique_submitters,
)
from utils.sql_utils import get_current_user
from config.constants import (
    CR_ID_COL,
    CR_STATUS_PENDING,
    CR_STATUS_APPROVED,
    CR_STATUS_REJECTED,
)


def render_review_panel(catalog: str, target_table: Optional[str] = None):
    """
    Render the review and approval panel.
    
    Args:
        catalog: Catalog name
        target_table: Optional target table to filter by
    """
    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.header("📋 Review & Approve Change Requests")
    
    current_user = get_current_user()
    
    # Get available options for dropdowns
    try:
        available_tables = get_unique_tables(catalog)
        available_submitters = get_unique_submitters(catalog)
    except Exception:
        available_tables = []
        available_submitters = []
    
    # Format table names for display (remove backticks, show clean format)
    def format_table_name(table_name: str) -> str:
        """Format table name for display by removing backticks."""
        if not table_name:
            return table_name
        # Remove backticks and return clean format
        clean_name = table_name.replace('`', '')
        # Optionally, show just the table name part (last component)
        parts = clean_name.split('.')
        if len(parts) >= 3:
            # Show as catalog.schema.table or just schema.table
            return f"{parts[1]}.{parts[2]}"
        elif len(parts) == 2:
            return f"{parts[0]}.{parts[1]}"
        return clean_name
    
    # Create mapping: display_name -> actual_table_name
    table_display_map = {}
    table_display_options = ["All"]
    
    for table in available_tables:
        display_name = format_table_name(table)
        table_display_map[display_name] = table
        table_display_options.append(display_name)
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            options=["All", "Pending", "Approved", "Rejected"],
            key="cr_status_filter",
        )
    
    with col2:
        # Find index of target_table if provided
        default_table_idx = 0
        if target_table:
            # Format target_table for comparison
            target_display = format_table_name(target_table)
            if target_display in table_display_options:
                default_table_idx = table_display_options.index(target_display)
        
        table_filter_display = st.selectbox(
            "Filter by Table",
            options=table_display_options,
            index=default_table_idx,
            key="cr_table_filter",
            help="Select a table to filter change requests",
        )
        
        # Map display name back to actual table name for filtering
        table_filter = table_display_map.get(table_filter_display) if table_filter_display != "All" else None
    
    with col3:
        # Build submitter options with "All" at the beginning
        submitter_options = ["All"] + available_submitters
        
        submitter_filter = st.selectbox(
            "Filter by Submitter",
            options=submitter_options,
            index=0,
            key="cr_submitter_filter",
            help="Select a submitter to filter change requests",
        )
    
    # Map filter values
    status_map = {
        "All": None,
        "Pending": CR_STATUS_PENDING,
        "Approved": CR_STATUS_APPROVED,
        "Rejected": CR_STATUS_REJECTED,
    }
    status_value = status_map.get(status_filter)
    # table_filter is already mapped to actual table name (or None if "All")
    table_value = table_filter
    submitter_value = submitter_filter if submitter_filter != "All" else None
    
    # Get change requests
    try:
        crs_df = get_change_requests(
            catalog=catalog,
            target_table=table_value,
            status=status_value,
            submitted_by=submitter_value,
        )
        
        if crs_df.empty:
            st.info("No change requests found matching the filters.")
            st.markdown("</div>", unsafe_allow_html=True)
            return
        
        # Display summary
        pending_count = len(crs_df[crs_df["status"] == CR_STATUS_PENDING])
        if pending_count > 0:
            st.warning(f"⚠️ {pending_count} pending change request(s) awaiting review")
        
        # Display change requests
        st.divider()
        
        for idx, cr_row in crs_df.iterrows():
            cr_id = cr_row["cr_id"]
            status = cr_row["status"]
            target_tbl = cr_row["target_table"]
            change_type = cr_row["change_type"]
            submitted_by = cr_row["submitted_by"]
            submitted_ts = cr_row["submitted_ts"]
            note = cr_row.get("note", "") or ""
            row_count = cr_row.get("row_count", 0)
            
            # Status badge color
            if status == CR_STATUS_PENDING:
                status_color = "🟡"
                status_bg = "#fff3cd"
            elif status == CR_STATUS_APPROVED:
                status_color = "✅"
                status_bg = "#d1e7dd"
            else:  # rejected
                status_color = "❌"
                status_bg = "#f8d7da"
            
            # Create expandable section for each CR
            with st.expander(
                f"{status_color} **CR {cr_id[:8]}...** | {target_tbl.split('.')[-1]} | "
                f"{change_type} | {row_count} row(s) | {submitted_by} | {submitted_ts}",
                expanded=(status == CR_STATUS_PENDING),
            ):
                # CR Details
                detail_cols = st.columns(2)
                
                with detail_cols[0]:
                    st.write("**Change Request Details:**")
                    st.write(f"- **ID:** `{cr_id}`")
                    st.write(f"- **Target Table:** `{target_tbl}`")
                    st.write(f"- **Type:** {change_type}")
                    st.write(f"- **Status:** {status}")
                    st.write(f"- **Row Count:** {row_count:,}")
                
                with detail_cols[1]:
                    st.write("**Submission Info:**")
                    st.write(f"- **Submitted By:** {submitted_by}")
                    st.write(f"- **Submitted At:** {submitted_ts}")
                    
                    if status == CR_STATUS_APPROVED:
                        approved_by = cr_row.get("approved_by", "")
                        approved_ts = cr_row.get("approved_ts", "")
                        if approved_by:
                            st.write(f"- **Approved By:** {approved_by}")
                        if approved_ts:
                            st.write(f"- **Approved At:** {approved_ts}")
                    
                    if status == CR_STATUS_REJECTED:
                        rejected_by = cr_row.get("rejected_by", "")
                        rejected_ts = cr_row.get("rejected_ts", "")
                        rejection_reason = cr_row.get("rejection_reason", "")
                        if rejected_by:
                            st.write(f"- **Rejected By:** {rejected_by}")
                        if rejected_ts:
                            st.write(f"- **Rejected At:** {rejected_ts}")
                        if rejection_reason:
                            st.write(f"- **Reason:** {rejection_reason}")
                
                if note:
                    st.info(f"**Note:** {note}")
                
                # Show staging rows
                try:
                    staging_rows = get_staging_rows(catalog, target_tbl, cr_id)
                    
                    if not staging_rows.empty:
                        # Remove CR_ID column for display
                        display_rows = staging_rows.drop(columns=[CR_ID_COL])
                        
                        st.write("**Data to be reviewed:**")
                        st.dataframe(
                            display_rows,
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.warning("No staging rows found for this change request.")
                except Exception as e:
                    st.error(f"Error loading staging rows: {e}")
                
                # Action buttons (only for pending CRs)
                if status == CR_STATUS_PENDING:
                    st.divider()
                    
                    # Check if current user is the submitter (prevent self-approval)
                    is_self_submission = submitted_by == current_user
                    
                    if is_self_submission:
                        st.warning(
                            f"⚠️ **You cannot approve your own change request.** "
                            f"This was submitted by you ({submitted_by}). "
                            f"Please ask another user to review and approve it."
                        )
                    
                    action_cols = st.columns(3)
                    
                    with action_cols[0]:
                        approve_disabled = is_self_submission
                        if st.button(
                            "✅ Approve", 
                            key=f"approve_{cr_id}", 
                            type="primary",
                            disabled=approve_disabled,
                            help="You cannot approve your own change request" if approve_disabled else None
                        ):
                            try:
                                with st.spinner("Approving change request…"):
                                    approve_change_request(
                                        catalog=catalog,
                                        target_table=target_tbl,
                                        cr_id=cr_id,
                                        approved_by=current_user,
                                    )
                                st.success(f"Change request {cr_id[:8]}... approved successfully!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error approving change request: {e}")
                    
                    with action_cols[1]:
                        rejection_reason = st.text_input(
                            "Rejection reason (optional)",
                            key=f"reject_reason_{cr_id}",
                            placeholder="Enter reason for rejection...",
                        )
                    
                    with action_cols[2]:
                        reject_disabled = is_self_submission
                        if st.button(
                            "❌ Reject", 
                            key=f"reject_{cr_id}",
                            disabled=reject_disabled,
                            help="You cannot reject your own change request" if reject_disabled else None
                        ):
                            try:
                                with st.spinner("Rejecting change request…"):
                                    reject_change_request(
                                        catalog=catalog,
                                        target_table=target_tbl,
                                        cr_id=cr_id,
                                        rejected_by=current_user,
                                        reason=rejection_reason or "",
                                    )
                                st.success(f"Change request {cr_id[:8]}... rejected.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error rejecting change request: {e}")
        
        st.markdown("</div>", unsafe_allow_html=True)
        
    except Exception as e:
        st.error(f"Error loading change requests: {e}")
        st.markdown("</div>", unsafe_allow_html=True)

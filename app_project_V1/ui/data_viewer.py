import streamlit as st
import pandas as pd
import os

from config.setup import thousands_num_cfg
from utils.data_utils import _safe_clear_data_cache
from typing import List


DEFAULT_MAX_VIEWER_ROWS = max(
    1, int(os.getenv("DATA_VIEWER_MAX_ROWS", "50000"))
)


def inline_data_viewer(data: pd.DataFrame, all_cols: List):
    # -----------------------------------------------------------------------------
    # Inline data viewer of latest version
    # -----------------------------------------------------------------------------

    st.markdown("<div class='app-card'>", unsafe_allow_html=True)
    st.info(
        "Hover over the grey column on the left to show **checkboxes**. Select one or more rows. Use **Load selected row into form** to copy selected row into the **Add / Edit Row** section for editing, or use **Delete selected** to remove multiple rows at once."
    )

    if st.button("🔄 Refresh table", key="btn_refresh"):
        _safe_clear_data_cache()
        st.session_state.pop("row_selection", None)
        st.rerun()

    latest = pd.DataFrame()
    displayed = pd.DataFrame()
    if not data.empty:
        latest = data.copy()
        latest = latest.sort_values(by="__KEY", ascending=False)
        # Hide "empty snapshot" marker rows (used when a user deletes all rows).
        # We reserve __KEY == 0 for this purpose.
        try:
            latest = latest[latest["__KEY"] != 0]
        except Exception:
            pass

        displayed = latest.head(DEFAULT_MAX_VIEWER_ROWS).copy()

        if len(latest) > len(displayed):
            st.warning(
                "Showing the first "
                f"{len(displayed):,} of {len(latest):,} rows to keep the viewer responsive. "
                "Download latest version as CSV for the full snapshot. "
            )

    event = st.dataframe(
        displayed if not displayed.empty else pd.DataFrame(columns=all_cols),
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key="row_selection",
        column_config=thousands_num_cfg(displayed),
    )

    st.markdown("</div>", unsafe_allow_html=True)

    return latest, displayed, event

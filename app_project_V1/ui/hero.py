import base64
import os

import streamlit as st


def render_hero(
    title: str,
    eyebrow: str,
    logo_path: str | None = None,
) -> None:
    """Render a compact, neutral page header."""
    st.markdown("<div class='hero'>", unsafe_allow_html=True)
    left, right = st.columns([5, 1], gap="large")
    with left:
        st.caption(eyebrow)
        st.markdown(f"<h1>{title}</h1>", unsafe_allow_html=True)
    with right:
        try:
            if logo_path and os.path.exists(logo_path) and logo_path.endswith(".png"):
                with open(logo_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                st.markdown(
                    f"<img src='data:image/png;base64,{b64}' class='app-logo' alt='Application logo' />",
                    unsafe_allow_html=True,
                )
            elif logo_path:
                st.image(logo_path, use_column_width=True)
        except Exception:
            pass
    st.markdown("</div>", unsafe_allow_html=True)

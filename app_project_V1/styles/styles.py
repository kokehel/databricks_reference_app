import streamlit as st


# -----------------------------------------------------------------------------
# UI Theming / Styling helpers
# -----------------------------------------------------------------------------
def inject_global_styles() -> None:
    """Inject a neutral, customer-agnostic Streamlit theme."""
    st.markdown(
        """
        <style>
        :root {
            --app-bg: #f8fafc;
            --surface: #ffffff;
            --surface-subtle: #f1f5f9;
            --border: #d6dde6;
            --text: #111827;
            --text-muted: #5b6472;
            --accent: #2563eb;
            --accent-hover: #1d4ed8;
        }

        /* Remove Streamlit's top decoration/header bar */
        [data-testid="stDecoration"],
        [data-testid="stHeader"] { display: none !important; }
        .stApp {
            background: var(--app-bg) !important;
            color: var(--text) !important;
            padding-top: 0 !important;
        }

        /* Sidebar styling */
        [data-testid="stSidebar"] {
            background: var(--surface) !important;
            border-right: 1px solid var(--border) !important;
        }
        [data-testid="stSidebar"] * {
            color: var(--text) !important;
        }
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] small,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: var(--text-muted) !important;
        }

        /* Buttons */
        .stButton > button,
        .stDownloadButton > button,
        .stForm button,
        .stFileUploader button,
        [data-testid="baseButton-primary"],
        [data-testid="baseButton-secondary"] {
            background: var(--surface) !important;
            color: var(--text) !important;
            border: 1px solid var(--border) !important;
            border-radius: 8px !important;
            padding: 0.55rem 0.9rem !important;
            font-weight: 600 !important;
            box-shadow: none !important;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        .stForm button:hover,
        .stFileUploader button:hover,
        [data-testid="baseButton-primary"]:hover,
        [data-testid="baseButton-secondary"]:hover {
            background: var(--surface-subtle) !important;
            border-color: #b7c1cf !important;
            color: var(--text) !important;
        }
        [data-testid="baseButton-primary"] {
            background: var(--accent) !important;
            border-color: var(--accent) !important;
            color: #ffffff !important;
        }
        [data-testid="baseButton-primary"]:hover {
            background: var(--accent-hover) !important;
            border-color: var(--accent-hover) !important;
            color: #ffffff !important;
        }

        /* Inputs */
        .stTextInput > div > div > input,
        .stNumberInput input,
        .stDateInput input,
        .stFileUploader label {
            border-radius: 8px !important;
        }

        /* Schema selectbox styling */
        [data-testid="stSidebar"] .stSelectbox > div > div > select,
        [data-testid="stSidebar"] .stSelectbox > div > div > div,
        [data-testid="stSidebar"] .stSelectbox > div > div > div > div,
        [data-testid="stSidebar"] .stSelectbox > div > div > div > div > div {
            background: var(--surface) !important;
            color: var(--text) !important;
        }
        [data-testid="stSidebar"] .stSelectbox option {
            background: var(--surface) !important;
            color: var(--text) !important;
        }

        .app-card {
            background: transparent !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            padding: 0 !important;
            margin: 0 0 0.75rem 0 !important;
        }

        .hero {
            background: transparent !important;
            box-shadow: none !important;
            border-bottom: 1px solid var(--border) !important;
            border-radius: 0 !important;
            padding: 0 0 0.75rem 0 !important;
            margin: 0 0 1rem 0 !important;
        }
        .hero::before, .hero::after { display: none !important; content: none !important; }
        .hero h1 {
            color: var(--text) !important;
            font-size: 1.75rem !important;
            font-weight: 700 !important;
            letter-spacing: 0 !important;
            line-height: 1.2 !important;
            margin: 0 !important;
        }
        .app-logo {
            display: block;
            height: auto;
            margin-left: auto;
            max-height: 48px;
            max-width: 140px;
            object-fit: contain;
        }
        .stDataFrame {
            background: transparent !important;
            box-shadow: none !important;
            border-radius: 0 !important;
        }
        [data-testid="stAlert"], .stAlert { background: transparent !important; box-shadow: none !important; border: 0 !important; padding: 0.25rem 0 !important; }
        [data-testid="stMarkdownContainer"] .stAlert { background: transparent !important; }
        hr, [data-testid="stDivider"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

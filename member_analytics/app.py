"""Streamlit entry point for the Natural Language Analytics System."""

from __future__ import annotations

import streamlit as st

from agent import ask_database
from analytics import (
    get_channel_distribution,
    get_monthly_registrations,
    get_network_distribution,
    get_status_distribution,
    get_summary_metrics,
)
from database import test_connection

st.set_page_config(
    page_title="Member Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      [data-testid="stMetric"] {
        background: linear-gradient(145deg, #ffffff, #f5f7fb);
        border: 1px solid #e7ebf3;
        border-radius: 14px;
        padding: 18px;
        box-shadow: 0 6px 20px rgba(30, 41, 59, 0.06);
      }
      .hero {
        padding: 1.2rem 1.4rem;
        border-radius: 16px;
        background: linear-gradient(120deg, #132a46, #245b8f);
        color: white;
        margin-bottom: 1.2rem;
      }
      .hero h1 { margin: 0; font-size: 2rem; }
      .hero p { margin: .35rem 0 0; opacity: .85; }
      .answer {
        padding: 1rem 1.2rem;
        border-left: 5px solid #21a179;
        background: #eefaf6;
        border-radius: 8px;
        font-size: 1.08rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=60, show_spinner=False)
def load_dashboard_data():
    return (
        get_summary_metrics(),
        get_status_distribution(),
        get_network_distribution(),
        get_monthly_registrations(),
        get_channel_distribution(),
    )


def dashboard_page() -> None:
    header("📊 Analytics Dashboard", "Live insights from PostgreSQL member-account data")
    try:
        metrics, status, network, monthly, channel = load_dashboard_data()
    except Exception as exc:
        st.error(f"Could not load dashboard data: {exc}")
        st.info("Check the database and column mappings in `.env`, then reload the page.")
        return

    columns = st.columns(5)
    columns[0].metric("Total Accounts", f"{metrics['total_accounts']:,}")
    columns[1].metric("Approved", f"{metrics['approved']:,}")
    columns[2].metric("Pending", f"{metrics['pending']:,}")
    columns[3].metric("Rejected", f"{metrics['rejected']:,}")
    columns[4].metric("Total Amount", f"{metrics['total_amount']:,.2f}")

    left, right = st.columns(2)
    with left:
        st.subheader("Accounts by Status")
        st.bar_chart(status, x="status", y="accounts", color="#245b8f")
    with right:
        st.subheader("Network Distribution")
        st.plotly_chart(
            {
                "data": [
                    {
                        "labels": network["network"],
                        "values": network["accounts"],
                        "type": "pie",
                        "hole": 0.42,
                    }
                ],
                "layout": {"margin": {"l": 10, "r": 10, "t": 10, "b": 10}},
            },
            width="stretch",
        )

    st.subheader("Monthly Registrations")
    st.line_chart(monthly, x="month", y="registrations", color="#21a179")

    st.subheader("Accounts by Channel")
    st.bar_chart(channel, x="channel", y="accounts", horizontal=True, color="#da7b35")


DEMO_QUESTIONS = [
    "How many approved members are there?",
    "Which network has the highest number of members?",
    "How many records were created this month?",
    "Show members by channel.",
    "What is the total amount collected?",
    "How many pending applications exist?",
    "Which status has the highest count?",
    "Show the top ten product codes.",
]


def ask_page() -> None:
    header("🤖 Ask the Database", "Turn a plain-language question into safe, read-only SQL")

    selected = st.selectbox(
        "Try a demonstration question",
        ["Write my own question…", *DEMO_QUESTIONS],
    )
    default_question = "" if selected.startswith("Write") else selected

    with st.form("ask_database_form"):
        question = st.text_input(
            "Question",
            value=default_question,
            placeholder="e.g. Which network has the most members?",
        )
        submitted = st.form_submit_button("Ask database", type="primary")

    if submitted:
        with st.spinner("Generating and checking SQL…"):
            try:
                result = ask_database(question)
            except Exception as exc:
                st.error(f"Could not answer the question: {exc}")
                return

        st.success(result.answer)
        st.subheader("Generated SQL")
        st.code(result.sql, language="sql")
        st.subheader("Result Table")
        st.dataframe(result.data, width="stretch", hide_index=True)
        st.caption("Generated SQL is validated and executed in a read-only transaction.")


def about_page() -> None:
    header("ℹ️ About", "Natural-language analytics in one Streamlit application")
    st.subheader("How it works")
    st.code(
        """
                       User
                         │
                   Streamlit UI
              ┌──────────┴──────────┐
              │                     │
       Dashboard Engine      AI Database Agent
              │                     │
              └──────────┬──────────┘
                         │
                  PostgreSQL Database
        """,
        language=None,
    )
    st.markdown(
        """
        The dashboard runs predefined analytical queries for fast, consistent
        metrics and visualizations. The AI assistant receives the live table
        schema, translates a user's question into PostgreSQL, validates it as
        read-only, executes it, and explains the result.

        **Demo safety:** generated queries run in a read-only transaction, have a
        10-second timeout, and return at most 200 rows.
        """
    )


with st.sidebar:
    st.title("Member Analytics")
    st.caption("Natural Language Analytics System")
    page = st.radio(
        "Navigation",
        ["📊 Analytics Dashboard", "🤖 Ask Database", "ℹ️ About"],
        label_visibility="collapsed",
    )
    st.divider()
    connected, detail = test_connection()
    if connected:
        st.success(f"Database connected\n\n`{detail}`")
    else:
        st.error("Database disconnected")
        with st.expander("Connection details"):
            st.caption(detail)

if page.startswith("📊"):
    dashboard_page()
elif page.startswith("🤖"):
    ask_page()
else:
    about_page()

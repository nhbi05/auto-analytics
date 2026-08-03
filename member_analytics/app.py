"""Streamlit entry point for the Natural Language Analytics System."""

from __future__ import annotations

import html

import plotly.express as px
import plotly.graph_objects as go
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
from charts import CHART_COLORS, style_chart
from exports import build_graph_download

st.set_page_config(
    page_title="Member Analytics",
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
      .notice {
        padding: .8rem 1rem;
        border: 1px solid #d9dee8;
        border-left-width: 4px;
        border-radius: 6px;
        margin: .5rem 0;
      }
      .notice-error {
        background: #fff3f3;
        border-color: #c94b4b;
      }
      .notice-info {
        background: #f3f7fb;
        border-color: #3973a8;
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


def notice(message: str, kind: str = "info") -> None:
    safe_message = html.escape(message).replace("\n", "<br>")
    st.markdown(
        f'<div class="notice notice-{kind}">{safe_message}</div>',
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
    header("Analytics Dashboard", "Live insights from the SmartLife database")
    try:
        metrics, status, network, monthly, channel = load_dashboard_data()
    except Exception as exc:
        notice(f"Could not load dashboard data: {exc}", "error")
        notice("Check the database and column mappings in .env, then reload the page.")
        return

    columns = st.columns(5)
    columns[0].metric("Total Accounts", f"{metrics['total_accounts']:,}")
    columns[1].metric("Approved", f"{metrics['approved']:,}")
    columns[2].metric("Pending", f"{metrics['pending']:,}")
    columns[3].metric("Rejected", f"{metrics['rejected']:,}")
    columns[4].metric("Collected Amount", f"{metrics['total_amount']:,.2f}")

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
    "Project monthly registrations for the next 6 months.",
    "Forecast the total monthly amount for the next year.",
]


def render_answer_chart(result) -> None:
    if result.chart_data is None or result.chart_type == "none":
        return

    chart_title = result.chart_title or "Visual result"
    if result.analysis_type == "projection":
        figure = go.Figure()
        if "series" in result.chart_data.columns:
            for index, (series, series_data) in enumerate(
                result.chart_data.groupby("series", sort=True)
            ):
                color = CHART_COLORS[index % len(CHART_COLORS)]
                figure.add_trace(
                    go.Scatter(
                        x=series_data["period"],
                        y=series_data["actual"],
                        name=f"{series} historical",
                        legendgroup=str(series),
                        mode="lines+markers",
                        line={"color": color, "width": 3},
                        hovertemplate="%{y:,.0f}<extra></extra>",
                    )
                )
                figure.add_trace(
                    go.Scatter(
                        x=series_data["period"],
                        y=series_data["projected"],
                        name=f"{series} projected",
                        legendgroup=str(series),
                        mode="lines+markers",
                        line={"color": color, "width": 3, "dash": "dash"},
                        hovertemplate="%{y:,.0f}<extra></extra>",
                    )
                )
        else:
            figure.add_trace(
                go.Scatter(
                    x=result.chart_data["period"],
                    y=result.chart_data["actual"],
                    name="Historical",
                    mode="lines+markers",
                    line={"color": "#245b8f", "width": 3},
                    hovertemplate="%{y:,.0f}<extra></extra>",
                )
            )
            figure.add_trace(
                go.Scatter(
                    x=result.chart_data["period"],
                    y=result.chart_data["projected"],
                    name="Projected",
                    mode="lines+markers",
                    line={"color": "#21a179", "width": 3, "dash": "dash"},
                    hovertemplate="%{y:,.0f}<extra></extra>",
                )
            )
        figure.update_layout(
            hovermode="x unified",
            margin={"l": 10, "r": 10, "t": 20, "b": 10},
            xaxis_title=None,
            yaxis_title=result.y_column.replace("_", " ").title(),
            legend={"orientation": "h", "y": -0.25, "x": 0},
        )
        figure.update_yaxes(
            tickformat=",.0f",
            exponentformat="none",
            separatethousands=True,
        )
    elif result.chart_type == "line":
        figure = px.line(
            result.chart_data,
            x=result.x_column,
            y=result.y_column,
            markers=True,
        )
    elif result.chart_type in {"pie", "donut"}:
        figure = px.pie(
            result.chart_data,
            names=result.x_column,
            values=result.y_column,
            hole=0.45 if result.chart_type == "donut" else 0,
        )
        figure.update_traces(
            textinfo="label+percent",
            hovertemplate="%{label}: %{value:,.0f} (%{percent})<extra></extra>",
        )
    elif result.chart_type == "area":
        figure = px.area(
            result.chart_data,
            x=result.x_column,
            y=result.y_column,
            markers=True,
        )
    elif result.chart_type == "scatter":
        figure = px.scatter(
            result.chart_data,
            x=result.x_column,
            y=result.y_column,
        )
    elif result.chart_type == "histogram":
        figure = px.histogram(
            result.chart_data,
            x=result.x_column,
        )
    elif result.chart_type == "box":
        if result.y_column:
            figure = px.box(
                result.chart_data,
                x=result.x_column,
                y=result.y_column,
                points="outliers",
            )
        else:
            figure = px.box(
                result.chart_data,
                y=result.x_column,
                points="outliers",
            )
    elif result.chart_type == "funnel":
        figure = px.funnel(
            result.chart_data,
            x=result.y_column,
            y=result.x_column,
        )
    else:
        figure = px.bar(
            result.chart_data,
            x=result.x_column,
            y=result.y_column,
        )
    if result.chart_type not in {"pie", "donut"}:
        figure.update_xaxes(
            exponentformat="none",
            separatethousands=True,
        )
        figure.update_yaxes(
            exponentformat="none",
            separatethousands=True,
        )
    style_chart(
        figure,
        title=chart_title,
        chart_type=(
            "projection"
            if result.analysis_type == "projection"
            else result.chart_type
        ),
    )
    st.plotly_chart(
        figure,
        width="stretch",
        theme=None,
        config={"displayModeBar": False},
    )
    filename, graph_png = build_graph_download(figure, chart_title)
    st.download_button(
        "Download graph",
        data=graph_png,
        file_name=filename,
        mime="image/png",
        on_click="ignore",
    )
    if result.analysis_type == "projection":
        st.caption(
            "Projection uses a linear trend from up to 24 recent complete months. "
            "It is an estimate, not a guaranteed outcome."
        )


def ask_page() -> None:
    selected = st.selectbox(
        "Try a demonstration question",
        ["Write my own question...", *DEMO_QUESTIONS],
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
        with st.spinner("Generating and checking SQL..."):
            try:
                result = ask_database(question)
            except Exception as exc:
                notice(f"Could not answer the question: {exc}", "error")
                return

        safe_answer = html.escape(result.answer).replace("\n", "<br>")
        st.markdown(
            f'<div class="answer">{safe_answer}</div>',
            unsafe_allow_html=True,
        )
        render_answer_chart(result)
        st.subheader(
            "Historical data SQL"
            if result.analysis_type == "projection"
            else "Generated SQL"
        )
        st.code(result.sql, language="sql")
        st.subheader(
            "Projected Values"
            if result.analysis_type == "projection"
            else "Result Table"
        )
        st.dataframe(result.data, width="stretch", hide_index=True)
        st.caption("Generated SQL is validated and executed in a read-only transaction.")


def about_page() -> None:
    header("About", "Natural-language analytics in one Streamlit application")
    st.subheader("How it works")
    st.code(
        """
                       User
                         |
                   Streamlit UI
              +----------+----------+
              |                     |
       Dashboard Engine      AI Database Agent
              |                     |
              +----------+----------+
                         |
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
        30-second timeout, and return at most 200 rows.
        """
    )


with st.sidebar:
    st.title("Member Analytics")
    st.caption("Natural Language Analytics System")
    page = st.radio(
        "Navigation",
        ["Analytics Dashboard", "Ask Database", "About"],
        label_visibility="collapsed",
    )
    st.divider()
    connected, detail = test_connection()
    if connected:
        st.markdown("**Database connected**")
        st.caption(detail)
    else:
        notice("Database disconnected", "error")
        with st.expander("Connection details"):
            st.caption(detail)

if page == "Analytics Dashboard":
    dashboard_page()
elif page == "Ask Database":
    ask_page()
else:
    about_page()

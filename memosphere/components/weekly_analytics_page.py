# memosphere/components/weekly_analytics_page.py
# Streamlit page – Weekly Analytics (Stage 6)
# Shows completion percentage, counts, streak, and a 4‑week trend.
# All data is fetched via the analytics service; UI labels percentages as ESTIMATES.

import streamlit as st
import pandas as pd

from memosphere.services.analytics_service import (
    get_weekly_completion_pct,
    get_weekly_counts,
    get_weekly_streak,
    get_weekly_trend,
)


def _current_user_id():
    """Return the mock user ID from session state, or None."""
    if "current_user" in st.session_state and st.session_state.current_user:
        return st.session_state.current_user.id
    return None


def show_weekly_analytics_page():
    """Render the Weekly Analytics page."""
    user_id = _current_user_id()
    if user_id is None:
        st.error("User not logged in. Please start the app from the main dashboard.")
        return

    st.title("📊 Weekly Analytics")
    st.caption("📌 Percentages are **ESTIMATES** – the database stores only the most recent "
               "last_completed date per routine; historical weekly trends are approximate.")

    # --- Week selection ---
    week_index = st.sidebar.selectbox(
        "Select week",
        options=[0, -1, -2, -3],
        format_func=lambda i: "Current week" if i == 0 else f"{'Last ' if i < 0 else ''}week {abs(i)}",
        index=0,
    )

    # --- Completion percentage ---
    pct = get_weekly_completion_pct(user_id, week_index=week_index)
    st.metric(
        label="Weekly completion %",
        value=f"{pct}%" if pct is not None else "N/A",
        help="Calculated as (routines completed last week ÷ total routines) × 100. "
             "Labelled as an ESTIMATE because only the latest last_completed date is stored.",
    )

    # --- Weekly counts ---
    counts = get_weekly_counts(user_id, week_index=week_index)
    c1, c2, c3 = st.columns(3)
    c1.metric("Completed", counts["completed"])
    c2.metric("Pending", counts["pending"])
    c3.metric("Missed", counts["missed"])

    # --- Streak ---
    streak = get_weekly_streak(user_id)
    st.metric("Current completion streak (weeks)", streak,
              help="Number of consecutive ISO weeks ending with the most recent week "
                   "in which at least one routine was marked completed.")

    # --- Trend chart (last 4 weeks) ---
    st.subheader("Completion trend (last 4 weeks)")
    trend = get_weekly_trend(user_id, weeks=4)
    weeks_labels = ["4 weeks ago", "3 weeks ago", "2 weeks ago", "Last week"]
    # pad with N/A if fewer than 4 weeks of data exist
    padded = trend + [None] * (4 - len(trend))
    chart_data = pd.DataFrame(
        {"Completion %": padded},
        index=weeks_labels,
    )
    st.line_chart(chart_data)

    st.info(
        "💡 The streak and trend calculations use the same ESTIMATE logic as the "
        "completion percentage – only the most recent last_completed date per routine "
        "is available, so historical accuracy is limited."
    )
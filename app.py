"""
STEP 4 – Streamlit Dashboard
Reads the same Postgres (Neon) used by the hunter bot.
Deploy on Streamlit Community Cloud – Main file path: app.py
"""
import os
import json
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Airdrop Hunter",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# DB connection (Streamlit secrets or env)
# ---------------------------------------------------------------------------
def get_database_url() -> str:
    # Streamlit Cloud: Settings → Secrets
    try:
        url = st.secrets.get("DATABASE_URL", "")
        if url:
            return url
    except Exception:
        pass
    return os.getenv("DATABASE_URL", "")


@st.cache_resource
def get_engine():
    url = get_database_url()
    if not url:
        return None
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=60)
def load_airdrops() -> pd.DataFrame:
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    q = text(
        """
        SELECT
            id, name, description, project_url, airdrop_url, chain,
            legitimacy_score, score_breakdown, reasons, risk_label, red_flags,
            participation_level, participation_tags,
            sources, source_links, status,
            first_seen, last_updated, last_scanned
        FROM airdrops
        ORDER BY legitimacy_score DESC NULLS LAST, last_updated DESC
        """
    )
    try:
        with engine.connect() as conn:
            df = pd.read_sql(q, conn)
        return df
    except Exception as e:
        st.session_state["_db_error"] = str(e)
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_scan_logs() -> pd.DataFrame:
    engine = get_engine()
    if engine is None:
        return pd.DataFrame()
    q = text(
        """
        SELECT id, started_at, finished_at, airdrops_found, airdrops_new,
               airdrops_updated, status, errors
        FROM scan_logs
        ORDER BY id DESC
        LIMIT 20
        """
    )
    try:
        with engine.connect() as conn:
            return pd.read_sql(q, conn)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Strategy labels (same as streamlit_filters / scoring engine)
# ---------------------------------------------------------------------------
STRATEGY_LABELS = {
    "zero_tx": "سخت‌گیرانه (بدون تراکنش)",
    "low_tx": "کم‌تراکنش",
    "medium_tx": "عادی",
    "high_tx": "همه روش‌ها",
}

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.title("🎯 Airdrop Hunter")
st.sidebar.caption("داشبورد فقط خواندنی — Claim دستی است")

if st.sidebar.button("🔄 تازه‌سازی داده"):
    load_airdrops.clear()
    load_scan_logs.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### استراتژی مشارکت")
st.sidebar.caption("از سخت‌گیرانه تا ساده")

selected_levels = []
for key, label in STRATEGY_LABELS.items():
    default = key == "zero_tx"
    if st.sidebar.checkbox(label, value=default, key=f"lvl_{key}"):
        selected_levels.append(key)

st.sidebar.markdown("---")
min_score = st.sidebar.slider("حداقل نمره", 0, 100, 40)
status_options = ["new", "notified", "done", "ignored", "scam"]
selected_status = st.sidebar.multiselect(
    "وضعیت",
    options=status_options,
    default=["new", "notified"],
)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
db_url = get_database_url()
if not db_url:
    st.error(
        "DATABASE_URL تنظیم نشده.\n\n"
        "در Streamlit Cloud: Settings → Secrets → این را بگذارید:\n\n"
        'DATABASE_URL = "postgresql://..."'
    )
    st.stop()

df = load_airdrops()
logs = load_scan_logs()

if df.empty and st.session_state.get("_db_error"):
    st.error(f"خطا در خواندن دیتابیس:\n{st.session_state['_db_error']}")
    st.stop()

# ---------------------------------------------------------------------------
# Bot status
# ---------------------------------------------------------------------------
st.title("Airdrop Hunter Dashboard")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("تعداد کل", len(df))
with c2:
    high = int((df["legitimacy_score"] >= 60).sum()) if not df.empty else 0
    st.metric("نمره ≥ ۶۰", high)
with c3:
    if not logs.empty:
        last = logs.iloc[0]
        st.metric("آخرین اسکن", str(last.get("status", "—")))
    else:
        st.metric("آخرین اسکن", "—")
with c4:
    if not logs.empty and pd.notna(logs.iloc[0].get("finished_at")):
        st.metric("زمان آخرین اسکن", str(logs.iloc[0]["finished_at"])[:19])
    else:
        st.metric("زمان آخرین اسکن", "—")

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
view = df.copy()
if not view.empty:
    if selected_levels and "participation_level" in view.columns:
        view = view[view["participation_level"].isin(selected_levels)]
    view = view[view["legitimacy_score"].fillna(0) >= min_score]
    if selected_status and "status" in view.columns:
        view = view[view["status"].isin(selected_status)]

    # Optional chain filter
    chains = sorted([c for c in view["chain"].dropna().unique().tolist() if c])
    if chains:
        pick = st.multiselect("فیلتر زنجیره (Chain)", options=chains, default=chains)
        if pick:
            view = view[view["chain"].isin(pick) | view["chain"].isna()]

# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📋 جدول", "📊 نمودار", "🛠 وضعیت بات"])

with tab1:
    if view.empty:
        st.info("موردی با این فیلترها پیدا نشد.")
    else:
        show = view[
            [
                c
                for c in [
                    "name",
                    "legitimacy_score",
                    "risk_label",
                    "participation_level",
                    "chain",
                    "status",
                    "project_url",
                    "airdrop_url",
                    "last_updated",
                ]
                if c in view.columns
            ]
        ].copy()
        show = show.rename(
            columns={
                "name": "نام",
                "legitimacy_score": "نمره",
                "risk_label": "ریسک",
                "participation_level": "استراتژی",
                "chain": "زنجیره",
                "status": "وضعیت",
                "project_url": "لینک پروژه",
                "airdrop_url": "لینک ایردراپ",
                "last_updated": "آخرین بروزرسانی",
            }
        )
        st.dataframe(show, use_container_width=True, height=420)

        # Detail expander for top rows
        st.markdown("### جزئیات (۵ مورد برتر)")
        for _, row in view.head(5).iterrows():
            with st.expander(f"{row.get('name', '?')} — {row.get('legitimacy_score', 0):.0f}/100"):
                st.write("**ریسک:**", row.get("risk_label"))
                st.write("**استراتژی:**", row.get("participation_level"))
                if row.get("project_url"):
                    st.write("**لینک:**", row.get("project_url"))
                reasons = row.get("reasons")
                if isinstance(reasons, str):
                    try:
                        reasons = json.loads(reasons)
                    except Exception:
                        reasons = [reasons]
                if reasons is not None and hasattr(reasons, "__iter__"):
                    st.write("**دلایل:**")
                    for r in list(reasons)[:8]:
                        st.write("-", r)
                flags = row.get("red_flags")
                if flags is not None and hasattr(flags, "__iter__") and len(list(flags)) > 0:
                    st.warning("Red flags: " + ", ".join(str(f) for f in list(flags)[:5]))

with tab2:
    if view.empty:
        st.info("داده‌ای برای نمودار نیست.")
    else:
        fig1 = px.histogram(
            view,
            x="legitimacy_score",
            nbins=20,
            title="توزیع نمره مشروعیت",
            labels={"legitimacy_score": "نمره"},
        )
        st.plotly_chart(fig1, use_container_width=True)

        if "risk_label" in view.columns:
            counts = view["risk_label"].value_counts().reset_index()
            counts.columns = ["risk_label", "count"]
            fig2 = px.pie(
                counts,
                names="risk_label",
                values="count",
                title="برچسب ریسک",
            )
            st.plotly_chart(fig2, use_container_width=True)

        if "participation_level" in view.columns:
            pc = view["participation_level"].value_counts().reset_index()
            pc.columns = ["level", "count"]
            fig3 = px.bar(pc, x="level", y="count", title="سطح مشارکت")
            st.plotly_chart(fig3, use_container_width=True)

with tab3:
    st.markdown("### لاگ اسکن‌های اخیر")
    if logs.empty:
        st.info("هنوز scan_log ثبت نشده.")
    else:
        st.dataframe(logs, use_container_width=True)
    st.caption(
        "ربات روی Render اجرا می‌شود. این داشبورد فقط از دیتابیس می‌خواند و "
        "هیچ Claim یا اتصال کیف‌پولی انجام نمی‌دهد."
    )

st.markdown("---")
st.caption(f"آخرین بارگذاری صفحه: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

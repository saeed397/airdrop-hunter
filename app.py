"""
STEP 4 – Streamlit Dashboard (with connection timeout)
Main file path on Streamlit Cloud: app.py
"""
import os
import json
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Airdrop Hunter",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Airdrop Hunter Dashboard")
st.caption("در حال بررسی تنظیمات...")


def get_database_url() -> str:
    try:
        url = st.secrets["DATABASE_URL"]
        if url:
            return str(url).strip()
    except Exception:
        pass
    return os.getenv("DATABASE_URL", "").strip()


db_url = get_database_url()
if not db_url:
    st.error(
        "DATABASE_URL پیدا نشد.\n\n"
        "Manage app → Settings → Secrets و این را بگذارید:\n\n"
        'DATABASE_URL = "postgresql://..."'
    )
    st.stop()

st.success("Secrets خوانده شد. در حال اتصال به دیتابیس (حداکثر ۱۵ ثانیه)...")

# Timeout so the page does not spin forever
engine = create_engine(
    db_url,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": 15,
        "options": "-c statement_timeout=15000",
    },
)

try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    st.success("اتصال به دیتابیس برقرار شد.")
except Exception as e:
    st.error("اتصال به Neon برقرار نشد.")
    st.code(str(e))
    st.info(
        "چک کنید:\n"
        "1) آدرس DATABASE_URL در Secrets درست باشد\n"
        "2) در Neon پروژه خاموش/پاک نشده باشد\n"
        "3) اگر در URL بود channel_binding=require را بردارید"
    )
    st.stop()


@st.cache_data(ttl=60)
def load_airdrops(_url: str) -> pd.DataFrame:
    eng = create_engine(
        _url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
    )
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
    with eng.connect() as conn:
        return pd.read_sql(q, conn)


@st.cache_data(ttl=60)
def load_scan_logs(_url: str) -> pd.DataFrame:
    eng = create_engine(
        _url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
    )
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
        with eng.connect() as conn:
            return pd.read_sql(q, conn)
    except Exception:
        return pd.DataFrame()


STRATEGY_LABELS = {
    "zero_tx": "سخت‌گیرانه (بدون تراکنش)",
    "low_tx": "کم‌تراکنش",
    "medium_tx": "عادی",
    "high_tx": "همه روش‌ها",
}

st.sidebar.title("🎯 فیلترها")
if st.sidebar.button("🔄 تازه‌سازی"):
    load_airdrops.clear()
    load_scan_logs.clear()
    st.rerun()

selected_levels = []
for key, label in STRATEGY_LABELS.items():
    if st.sidebar.checkbox(label, value=(key == "zero_tx"), key=f"lvl_{key}"):
        selected_levels.append(key)

min_score = st.sidebar.slider("حداقل نمره", 0, 100, 40)
selected_status = st.sidebar.multiselect(
    "وضعیت",
    ["new", "notified", "done", "ignored", "scam"],
    default=["new", "notified"],
)

try:
    df = load_airdrops(db_url)
except Exception as e:
    st.error("خواندن جدول airdrops خطا داد:")
    st.code(str(e))
    st.stop()

logs = load_scan_logs(db_url)

c1, c2, c3 = st.columns(3)
c1.metric("تعداد کل", len(df))
c2.metric("نمره ≥ ۶۰", int((df["legitimacy_score"] >= 60).sum()) if not df.empty else 0)
if not logs.empty:
    c3.metric("آخرین اسکن", str(logs.iloc[0].get("status", "—")))
else:
    c3.metric("آخرین اسکن", "—")

view = df.copy()
if not view.empty:
    if selected_levels and "participation_level" in view.columns:
        view = view[view["participation_level"].isin(selected_levels)]
    view = view[view["legitimacy_score"].fillna(0) >= min_score]
    if selected_status and "status" in view.columns:
        view = view[view["status"].isin(selected_status)]

tab1, tab2, tab3 = st.tabs(["📋 جدول", "📊 نمودار", "🛠 لاگ اسکن"])

with tab1:
    if view.empty:
        st.info("موردی با این فیلترها نیست. فیلتر استراتژی یا نمره را بازتر کنید.")
    else:
        cols = [
            c
            for c in [
                "name",
                "legitimacy_score",
                "risk_label",
                "participation_level",
                "chain",
                "status",
                "project_url",
                "last_updated",
            ]
            if c in view.columns
        ]
        st.dataframe(view[cols], use_container_width=True, height=420)
        for _, row in view.head(5).iterrows():
            with st.expander(f"{row.get('name', '?')} — {float(row.get('legitimacy_score') or 0):.0f}/100"):
                st.write("ریسک:", row.get("risk_label"))
                st.write("لینک:", row.get("project_url") or row.get("airdrop_url"))
                reasons = row.get("reasons")
                if reasons is not None:
                    if isinstance(reasons, str):
                        try:
                            reasons = json.loads(reasons)
                        except Exception:
                            reasons = [reasons]
                    for r in list(reasons)[:8]:
                        st.write("-", r)

with tab2:
    if view.empty:
        st.info("داده‌ای برای نمودار نیست.")
    else:
        st.plotly_chart(
            px.histogram(view, x="legitimacy_score", nbins=20, title="توزیع نمره"),
            use_container_width=True,
        )
        if "risk_label" in view.columns:
            counts = view["risk_label"].value_counts().reset_index()
            counts.columns = ["risk_label", "count"]
            st.plotly_chart(
                px.pie(counts, names="risk_label", values="count", title="ریسک"),
                use_container_width=True,
            )

with tab3:
    if logs.empty:
        st.info("لاگ اسکن خالی است.")
    else:
        st.dataframe(logs, use_container_width=True)

st.caption(f"UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}")

"""داشبورد ایردراپ — فارسی، فیلتر سخت‌گیرانه، توضیح تصمیم‌گیری"""
import os
import json
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="شکارچی ایردراپ",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# RTL برای متن فارسی
st.markdown(
    """
    <style>
    .block-container, .stMarkdown, .stCaption, .stExpander, label {
        direction: rtl;
        text-align: right;
    }
    [data-testid="stSidebar"] {
        direction: rtl;
        text-align: right;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

HELP = {
    "score": (
        "نمره مشروعیت (۰ تا ۱۰۰)\n\n"
        "بالای ۵۵ یعنی نسبتاً قابل‌بررسی است.\n"
        "بالای ۷۰ معمولاً بهتر است.\n"
        "زیر ۵۵ را فعلاً جدی نگیرید مگر خودتان تحقیق کنید."
    ),
    "strategy": (
        "نوع مشارکت\n\n"
        "• بدون تراکنش: فالو، دیسکورد، امتیاز — مناسب‌تر برای شما\n"
        "• کم‌تراکنش: کار سبک با هزینه کم\n"
        "• عادی: ممکن است سواپ یا کار متوسط بخواهد\n"
        "• همه روش‌ها: احتمال بریج، نقدینگی یا هزینه بیشتر\n\n"
        "اگر تراکنش نمی‌زنید، فقط «بدون تراکنش» را روشن بگذارید."
    ),
    "status": (
        "وضعیت در سیستم\n\n"
        "• جدید: تازه پیدا شده\n"
        "• اطلاع‌داده: به تلگرام رفته\n"
        "• انجام‌شده: خودتان Done زده‌اید\n"
        "• نادیده: Ignore کرده‌اید\n"
        "• مشکوک: پرچم قرمز / اسکم"
    ),
    "risk": (
        "برچسب ریسک\n\n"
        "نشان می‌دهد ربات چقدر پروژه را خطرناک دیده.\n"
        "اگر پرچم قرمز دارد، اول لینک را خودتان چک کنید."
    ),
    "decision": (
        "راهنمای تصمیم سریع\n\n"
        "۱) نمره زیر ۵۵ → فعلاً رد\n"
        "۲) «همه روش‌ها» و شما تراکنش نمی‌زنید → رد\n"
        "۳) وضعیت مشکوک → رد\n"
        "۴) نمره ۵۵–۷۰ + بدون/کم‌تراکنش → بررسی دستی لینک\n"
        "۵) نمره بالای ۷۰ + بدون تراکنش → اولویت بالاتر\n\n"
        "ربات Claim نمی‌کند؛ تصمیم نهایی با شماست."
    ),
    "min_score": (
        "حداقل نمره نمایش\n\n"
        "پیش‌فرض ۵۵ است تا لیست شلوغ نشود.\n"
        "اگر چیزی ندیدید، کمی عدد را پایین بیاورید."
    ),
    "chain": (
        "شبکه (چین)\n\n"
        "فقط شبکه‌هایی را نگه دارید که والت‌تان روی آن‌ها کار می‌کند."
    ),
}

STATUS_FA = {
    "new": "جدید",
    "notified": "اطلاع‌داده",
    "done": "انجام‌شده",
    "ignored": "نادیده",
    "scam": "مشکوک",
}
STATUS_EN = {v: k for k, v in STATUS_FA.items()}

STRATEGY_FA = {
    "zero_tx": "بدون تراکنش",
    "low_tx": "کم‌تراکنش",
    "medium_tx": "عادی",
    "high_tx": "همه روش‌ها",
}


def explain_airdrop(row) -> str:
    """ماتریس توضیح فارسی کاربردی برای یک ایردراپ."""
    name = str(row.get("name") or "این پروژه")
    try:
        score = float(row.get("legitimacy_score") or 0)
    except Exception:
        score = 0.0
    risk = str(row.get("risk_label") or "نامشخص")
    level = str(row.get("participation_level") or "")
    status = str(row.get("status") or "")
    chain = row.get("chain")
    link = row.get("project_url") or row.get("airdrop_url") or ""

    level_fa = STRATEGY_FA.get(level, level or "نامشخص")
    status_fa = STATUS_FA.get(status, status or "نامشخص")
    chain_fa = str(chain) if chain and str(chain) not in ("None", "nan", "") else "ثبت نشده"

    # نمره
    if score >= 75:
        score_txt = f"نمره {score:.0f} نسبتاً خوب است؛ ارزش بررسی بیشتری دارد."
    elif score >= 55:
        score_txt = f"نمره {score:.0f} متوسط است؛ عجله نکنید، فقط بررسی کنید."
    else:
        score_txt = f"نمره {score:.0f} پایین است؛ فعلاً اولویت ندهید."

    # ریسک
    risk_l = risk.lower()
    if "scam" in risk_l or status == "scam":
        risk_txt = "ریسک خیلی بالاست یا مشکوک علامت خورده؛ بهتر است رد کنید."
    elif "high" in risk_l or risk_l == "risky":
        risk_txt = "ریسک بالا/Risky است؛ اگر جلو می‌روید فقط با والت کم‌موجودی."
    elif "medium" in risk_l or "moderate" in risk_l:
        risk_txt = "ریسک متوسط است؛ لینک رسمی را خودتان چک کنید."
    elif "low" in risk_l or "safe" in risk_l:
        risk_txt = "از نظر ربات ریسک پایین‌تری دارد؛ باز هم احتیاط کنید."
    else:
        risk_txt = f"برچسب ریسک: {risk}."

    # مشارکت
    if level == "zero_tx":
        part_txt = "مشارکت «بدون تراکنش» است؛ برای شما مناسب‌تر است (بدون سواپ/بریج)."
    elif level == "low_tx":
        part_txt = "مشارکت کم‌تراکنش است؛ ممکن است کار سبک با هزینه کم بخواهد."
    elif level == "medium_tx":
        part_txt = "مشارکت عادی است؛ احتمال کار متوسط یا سواپ وجود دارد."
    elif level == "high_tx":
        part_txt = "ممکن است بریج/نقدینگی یا هزینه بیشتر بخواهد؛ اگر تراکنش نمی‌زنید رد کنید."
    else:
        part_txt = f"نوع مشارکت: {level_fa}."

    # وضعیت
    if status == "new":
        status_txt = "تازه پیدا شده و هنوز بررسی‌اش نکرده‌اید."
    elif status == "notified":
        status_txt = "قبلاً به تلگرام اطلاع داده شده."
    elif status == "done":
        status_txt = "قبلاً به‌عنوان انجام‌شده علامت خورده."
    elif status == "ignored":
        status_txt = "قبلاً نادیده گرفته‌اید."
    elif status == "scam":
        status_txt = "به‌عنوان مشکوک ثبت شده."
    else:
        status_txt = f"وضعیت: {status_fa}."

    # شبکه و لینک
    chain_txt = f"شبکه: {chain_fa}."
    if not link:
        link_txt = "لینک مستقیمی ثبت نشده؛ خودتان سایت رسمی را پیدا کنید."
    elif "coingecko.com" in str(link).lower():
        link_txt = "لینک بیشتر صفحه معرفی/قیمت است، نه لزوماً صفحه Claim."
    elif "twitter.com" in str(link).lower() or "x.com" in str(link).lower():
        link_txt = "لینک شبکه‌اجتماعی است؛ صفحه رسمی Claim را جدا پیدا کنید."
    else:
        link_txt = "یک لینک ثبت شده؛ قبل از اتصال والت، آدرس را با دقت چک کنید."

    # دلایل کوتاه
    reasons = row.get("reasons")
    if isinstance(reasons, str):
        try:
            reasons = json.loads(reasons)
        except Exception:
            reasons = [reasons]
    reason_bits = []
    if reasons is not None and not isinstance(reasons, float):
        for r in list(reasons)[:4]:
            s = str(r)
            if "Domain age" in s or "domain" in s.lower():
                reason_bits.append("دامنه قدیمی‌تر دیده شده (نقطه مثبت نسبی)")
            elif "SSL" in s:
                reason_bits.append("گواهی امنیتی سایت OK بوده")
            elif "CoinGecko" in s or "Trending" in s:
                reason_bits.append("در منابع عمومی دیده/ترند شده")
            elif "Single source" in s:
                reason_bits.append("فقط از یک منبع آمده؛ اطلاعات محدود است")
            elif "zero_tx" in s or "Zero-TX" in s:
                reason_bits.append("سطح مشارکت بدون تراکنش در نظر گرفته شده")
            elif "honeypot" in s.lower():
                reason_bits.append("احتمال هانی‌پات/خطر قرارداد")
            elif "red" in s.lower() or "flag" in s.lower():
                reason_bits.append("پرچم هشدار در بررسی‌ها")
            else:
                if len(s) < 80:
                    reason_bits.append(s)

    flags = row.get("red_flags")
    if isinstance(flags, str):
        try:
            flags = json.loads(flags)
        except Exception:
            flags = [flags]
    has_flags = bool(flags) and not isinstance(flags, float) and len(list(flags)) > 0

    # جمع‌بندی تصمیم
    if status == "scam" or has_flags and score < 50:
        decision = "پیشنهاد: فعلاً رد کنید."
    elif level == "high_tx":
        decision = "پیشنهاد: اگر نمی‌خواهید تراکنش بزنید، رد یا نادیده."
    elif score >= 70 and level in ("zero_tx", "low_tx"):
        decision = "پیشنهاد: اولویت بررسی بالاتر — با والت کم‌موجودی و لینک رسمی."
    elif score >= 55 and level in ("zero_tx", "low_tx"):
        decision = "پیشنهاد: ارزش یک بررسی دارد؛ عجله برای Claim نیست."
    else:
        decision = "پیشنهاد: اولویت پایین؛ فقط اگر خودتان پروژه را می‌شناسید."

    lines = [
        f"**{name}**",
        "",
        score_txt,
        risk_txt,
        part_txt,
        status_txt,
        chain_txt,
        link_txt,
    ]
    if reason_bits:
        lines.append("")
        lines.append("نکات ربات:")
        for b in reason_bits[:5]:
            lines.append(f"• {b}")
    if has_flags:
        lines.append("")
        lines.append("⚠ پرچم قرمز: " + "، ".join(str(f) for f in list(flags)[:4]))
    lines.append("")
    lines.append(decision)
    lines.append("")
    lines.append("یادآوری: ربات Claim نمی‌کند؛ تصمیم و ریسک با شماست.")
    return "\n".join(lines)


def get_database_url() -> str:
    try:
        url = st.secrets["DATABASE_URL"]
        if url:
            return str(url).strip().strip('"').strip("'")
    except Exception:
        pass
    return os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")


db_url = get_database_url()
if not db_url:
    st.error("آدرس دیتابیس تنظیم نشده.")
    st.caption("Manage app → Settings → Secrets → DATABASE_URL")
    st.stop()

clean_url = (
    db_url.replace("&channel_binding=require", "")
    .replace("channel_binding=require&", "")
    .replace("?channel_binding=require", "")
)

try:
    engine = create_engine(
        clean_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
    )
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
except Exception as e:
    st.error("اتصال به دیتابیس برقرار نشد.")
    st.code(str(e))
    st.stop()


@st.cache_data(ttl=60)
def load_airdrops(_url: str) -> pd.DataFrame:
    u = (
        _url.replace("&channel_binding=require", "")
        .replace("channel_binding=require&", "")
        .replace("?channel_binding=require", "")
    )
    eng = create_engine(u, pool_pre_ping=True, connect_args={"connect_timeout": 15})
    q = text(
        """
        SELECT id, name, description, project_url, airdrop_url, chain,
               legitimacy_score, score_breakdown, reasons, risk_label, red_flags,
               participation_level, participation_tags, sources, source_links,
               status, first_seen, last_updated, last_scanned
        FROM airdrops
        ORDER BY legitimacy_score DESC NULLS LAST, last_updated DESC
        """
    )
    with eng.connect() as conn:
        return pd.read_sql(q, conn)


@st.cache_data(ttl=60)
def load_logs(_url: str) -> pd.DataFrame:
    u = (
        _url.replace("&channel_binding=require", "")
        .replace("channel_binding=require&", "")
        .replace("?channel_binding=require", "")
    )
    eng = create_engine(u, pool_pre_ping=True, connect_args={"connect_timeout": 15})
    q = text(
        """
        SELECT id, started_at, finished_at, airdrops_found, airdrops_new,
               airdrops_updated, status, errors
        FROM scan_logs ORDER BY id DESC LIMIT 15
        """
    )
    try:
        with eng.connect() as conn:
            return pd.read_sql(q, conn)
    except Exception:
        return pd.DataFrame()


# سایدبار
st.sidebar.markdown("### فیلترها")
with st.sidebar.popover("راهنمای تصمیم"):
    st.markdown(HELP["decision"])
with st.sidebar.popover("نمره چیست؟"):
    st.markdown(HELP["score"])

min_score = st.sidebar.slider("حداقل نمره", 0, 100, 55)
with st.sidebar.popover("درباره حداقل نمره"):
    st.markdown(HELP["min_score"])

st.sidebar.markdown("#### نوع مشارکت")
with st.sidebar.popover("توضیح نوع مشارکت"):
    st.markdown(HELP["strategy"])

selected_levels = []
for key, label in STRATEGY_FA.items():
    default_on = key in ("zero_tx", "low_tx")
    if st.sidebar.checkbox(label, value=default_on, key=f"lvl_{key}"):
        selected_levels.append(key)

st.sidebar.markdown("#### وضعیت")
with st.sidebar.popover("توضیح وضعیت"):
    st.markdown(HELP["status"])

selected_status_fa = st.sidebar.multiselect(
    "وضعیت‌های نمایش",
    options=list(STATUS_FA.values()),
    default=[STATUS_FA["new"], STATUS_FA["notified"]],
)
selected_status = [STATUS_EN[x] for x in selected_status_fa if x in STATUS_EN]

if st.sidebar.button("به‌روزرسانی داده"):
    load_airdrops.clear()
    load_logs.clear()
    st.rerun()

try:
    df = load_airdrops(db_url)
except Exception as e:
    st.error("خواندن ایردراپ‌ها خطا داد.")
    st.code(str(e))
    st.stop()

logs = load_logs(db_url)

view = df.copy() if df is not None else pd.DataFrame()
if not view.empty:
    if selected_levels and "participation_level" in view.columns:
        view = view[view["participation_level"].isin(selected_levels)]
    if "legitimacy_score" in view.columns:
        view = view[view["legitimacy_score"].fillna(0) >= min_score]
    if selected_status and "status" in view.columns:
        view = view[view["status"].isin(selected_status)]

    chains = sorted([c for c in view["chain"].dropna().unique().tolist() if c])
    if chains:
        with st.sidebar.popover("توضیح شبکه"):
            st.markdown(HELP["chain"])
        pick = st.sidebar.multiselect("شبکه", options=chains, default=chains)
        if pick:
            view = view[view["chain"].isin(pick) | view["chain"].isna()]

st.title("شکارچی ایردراپ")
st.caption("فقط مشاهده و فیلتر — دریافت همیشه دستی است")

c1, c2, c3, c4 = st.columns(4)
c1.metric("کل در دیتابیس", len(df) if df is not None else 0)
c2.metric("نمایش بعد از فیلتر", len(view))
c3.metric(
    "آخرین اسکن",
    str(logs.iloc[0]["status"]) if logs is not None and not logs.empty else "—",
)
c4.metric(
    "زمان اسکن",
    str(logs.iloc[0]["finished_at"])[:16]
    if logs is not None and not logs.empty and pd.notna(logs.iloc[0].get("finished_at"))
    else "—",
)

tab1, tab2, tab3 = st.tabs(["لیست ایردراپ", "نمودار", "وضعیت ربات"])

with tab1:
    with st.popover("راهنمای این صفحه"):
        st.markdown(
            "کنار هر نام، علامت **؟** را بزنید تا توضیح تصمیم‌گیری همان ایردراپ باز شود."
        )
    with st.popover("ریسک یعنی چه؟"):
        st.markdown(HELP["risk"])

    if view.empty:
        st.warning(
            "با فیلتر فعلی چیزی نیست. حداقل نمره را کم کنید یا نوع مشارکت بیشتری انتخاب کنید."
        )
    else:
        show = view.copy()
        if "status" in show.columns:
            show["وضعیت"] = show["status"].map(lambda x: STATUS_FA.get(x, x))
        if "participation_level" in show.columns:
            show["مشارکت"] = show["participation_level"].map(
                lambda x: STRATEGY_FA.get(x, x)
            )
        cols = [
            c
            for c in [
                "name",
                "legitimacy_score",
                "risk_label",
                "مشارکت",
                "chain",
                "وضعیت",
                "project_url",
                "airdrop_url",
            ]
            if c in show.columns
        ]
        rename = {
            "name": "نام",
            "legitimacy_score": "نمره",
            "risk_label": "ریسک",
            "chain": "شبکه",
            "project_url": "لینک پروژه",
            "airdrop_url": "لینک ایردراپ",
        }
        st.dataframe(
            show[cols].rename(columns=rename),
            use_container_width=True,
            height=320,
        )

        st.markdown("#### جزئیات + توضیح تصمیم")
        for i, (_, row) in enumerate(view.head(15).iterrows()):
            score = float(row.get("legitimacy_score") or 0)
            name = str(row.get("name") or "?")
            col_a, col_b = st.columns([0.92, 0.08])
            with col_a:
                with st.expander(f"{name} — نمره {score:.0f}", expanded=False):
                    st.write("**ریسک:**", row.get("risk_label"))
                    st.write(
                        "**مشارکت:**",
                        STRATEGY_FA.get(
                            row.get("participation_level"),
                            row.get("participation_level"),
                        ),
                    )
                    st.write(
                        "**وضعیت:**",
                        STATUS_FA.get(row.get("status"), row.get("status")),
                    )
                    st.write("**شبکه:**", row.get("chain") or "—")
                    link = row.get("project_url") or row.get("airdrop_url")
                    if link:
                        st.write("**لینک:**", link)
                    reasons = row.get("reasons")
                    if isinstance(reasons, str):
                        try:
                            reasons = json.loads(reasons)
                        except Exception:
                            reasons = [reasons]
                    if reasons is not None and not isinstance(reasons, float):
                        st.write("**چرا این نمره؟**")
                        for r in list(reasons)[:6]:
                            st.write("-", r)
                    flags = row.get("red_flags")
                    if isinstance(flags, str):
                        try:
                            flags = json.loads(flags)
                        except Exception:
                            flags = [flags]
                    if flags is not None and not isinstance(flags, float) and list(flags):
                        st.error(
                            "پرچم قرمز: " + "، ".join(str(f) for f in list(flags)[:5])
                        )
            with col_b:
                with st.popover("؟"):
                    st.markdown(explain_airdrop(row))

with tab2:
    if view.empty:
        st.info("برای نمودار، فیلتر را بازتر کنید.")
    else:
        st.plotly_chart(
            px.histogram(view, x="legitimacy_score", nbins=15, title="پراکندگی نمره"),
            use_container_width=True,
        )
        if "risk_label" in view.columns:
            counts = view["risk_label"].value_counts().reset_index()
            counts.columns = ["risk_label", "count"]
            st.plotly_chart(
                px.pie(
                    counts, names="risk_label", values="count", title="سهم برچسب ریسک"
                ),
                use_container_width=True,
            )

with tab3:
    st.caption("ربات روی Render کار می‌کند؛ این صفحه فقط گزارش می‌خواند.")
    if logs is None or logs.empty:
        st.info("هنوز لاگ اسکنی نیست.")
    else:
        st.dataframe(logs, use_container_width=True)

st.markdown("---")
st.caption(
    f"آخرین بارگذاری: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC — Claim همیشه دستی"
)

"""
Streamlit strategy filter helpers.
Used in the dashboard (STEP 4) to show checkboxes from strictest → easiest.

How it works in the UI:
  User selects one or more participation strategies via checkboxes.
  Only airdrops whose participation_level is in the selected set are shown.
"""
from typing import List, Set
import pandas as pd

# Re-export levels so Streamlit can import from one place
from src.scoring.engine import PARTICIPATION_LEVELS


# Order shown in UI (strictest first)
STRATEGY_ORDER = ["zero_tx", "low_tx", "medium_tx", "high_tx"]


def get_strategy_checkbox_options() -> List[dict]:
    """
    Returns list of options for Streamlit checkboxes.
    Each item: {key, label_fa, label_en, description}
    """
    options = []
    for key in STRATEGY_ORDER:
        info = PARTICIPATION_LEVELS[key]
        options.append({
            "key": key,
            "label_fa": info["label_fa"],
            "label_en": info["label_en"],
            "description": info["description"],
        })
    return options


def filter_by_participation(
    df: pd.DataFrame,
    selected_levels: List[str],
) -> pd.DataFrame:
    """
    Filter a DataFrame of airdrops by selected participation levels.

    Args:
        df: must contain column 'participation_level'
        selected_levels: list of keys e.g. ["zero_tx", "low_tx"]

    Returns:
        Filtered DataFrame (empty if nothing selected)
    """
    if df is None or df.empty:
        return df
    if not selected_levels:
        return df.iloc[0:0]  # empty
    if "participation_level" not in df.columns:
        return df
    return df[df["participation_level"].isin(selected_levels)].copy()


def render_strategy_checkboxes(st_module) -> List[str]:
    """
    Renders the strategy checkboxes inside a Streamlit sidebar or container.
    Call this from app.py:

        selected = render_strategy_checkboxes(st)

    Returns list of selected level keys.
    """
    st = st_module
    st.markdown("### استراتژی دریافت ایردراپ")
    st.caption("از سخت‌گیرانه‌ترین تا ساده‌ترین — هر کدام را که می‌خواهید تیک بزنید")

    selected: List[str] = []
    options = get_strategy_checkbox_options()

    # Default: only the strictest one checked (good for Iran / no-TX preference)
    defaults = {"zero_tx": True, "low_tx": False, "medium_tx": False, "high_tx": False}

    for opt in options:
        checked = st.checkbox(
            f"**{opt['label_fa']}**",
            value=defaults.get(opt["key"], False),
            key=f"strategy_{opt['key']}",
            help=opt["description"],
        )
        if checked:
            selected.append(opt["key"])

    if not selected:
        st.warning("حداقل یک استراتژی را انتخاب کنید.")
    else:
        labels = [PARTICIPATION_LEVELS[k]["label_fa"] for k in selected]
        st.success("فعال: " + " | ".join(labels))

    return selected

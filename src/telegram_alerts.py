"""
STEP 3 – Telegram alerts for high-score airdrops.

- Sends message when legitimacy_score >= ALERT_SCORE_THRESHOLD
- Inline buttons: Mark as Done / Ignore
- Bot runs on the server; you only read messages on your phone
- NO wallet / private key / claim logic
"""
from typing import Optional, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from src.config import settings
from src.utils.logger import log
from src.db.database import get_db
from src.db.models import Airdrop


def _format_message(
    name: str,
    score: float,
    risk_label: str,
    breakdown: Optional[dict],
    reasons: Optional[list],
    red_flags: Optional[list],
    links: Optional[list],
    participation_level: Optional[str],
    airdrop_id: str,
) -> str:
    """Build HTML message body for Telegram."""
    lines = [
        f"<b>🎯 {name}</b>",
        f"Score: <b>{score:.0f}/100</b>  |  {risk_label}",
    ]
    if participation_level:
        lines.append(f"Participation: <code>{participation_level}</code>")

    if breakdown:
        lines.append("")
        lines.append("<b>Breakdown</b>")
        for k, v in breakdown.items():
            lines.append(f"• {k}: {v:.0f}")

    if red_flags:
        lines.append("")
        lines.append("<b>⚠ Red flags</b>")
        for f in red_flags[:5]:
            lines.append(f"• {f}")

    if reasons:
        lines.append("")
        lines.append("<b>Reasons</b>")
        for r in reasons[:6]:
            lines.append(f"• {r}")

    if links:
        lines.append("")
        lines.append("<b>Links</b>")
        for url in links[:4]:
            if url:
                lines.append(f"• {url}")

    lines.append("")
    lines.append(f"<code>id:{airdrop_id}</code>")
    lines.append("<i>Claim is always MANUAL. Bot never connects a wallet.</i>")
    return "\n".join(lines)


def _keyboard(airdrop_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Done", callback_data=f"done:{airdrop_id}"),
                InlineKeyboardButton("⏭ Ignore", callback_data=f"ignore:{airdrop_id}"),
            ]
        ]
    )


async def send_airdrop_alert(
    *,
    airdrop_id: str,
    name: str,
    score: float,
    risk_label: str,
    breakdown: Optional[dict] = None,
    reasons: Optional[list] = None,
    red_flags: Optional[list] = None,
    links: Optional[list] = None,
    participation_level: Optional[str] = None,
) -> bool:
    """
    Send one alert to TELEGRAM_CHAT_ID.
    Returns True if sent successfully.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        log.warning("Telegram not configured (TOKEN or CHAT_ID missing) – skip alert")
        return False

    if score < settings.ALERT_SCORE_THRESHOLD:
        return False

    text = _format_message(
        name=name,
        score=score,
        risk_label=risk_label,
        breakdown=breakdown,
        reasons=reasons,
        red_flags=red_flags,
        links=links,
        participation_level=participation_level,
        airdrop_id=airdrop_id,
    )

    try:
        app = Application.builder().token(token).build()
        await app.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=_keyboard(airdrop_id),
            disable_web_page_preview=True,
        )
        log.info(f"Telegram alert sent for {name} ({score:.0f})")
        return True
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


async def on_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Done / Ignore inline buttons."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    try:
        action, airdrop_id = query.data.split(":", 1)
    except ValueError:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    new_status = "done" if action == "done" else "ignored"
    try:
        with get_db() as db:
            row = db.get(Airdrop, airdrop_id)
            if row:
                row.status = new_status
                log.info(f"Airdrop {airdrop_id} marked as {new_status}")
    except Exception as e:
        log.error(f"Failed to update status for {airdrop_id}: {e}")

    label = "✅ Done" if new_status == "done" else "⏭ Ignored"
    try:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"{label} — saved.")
    except Exception:
        pass


# Global app for long-running polling (started from server lifespan)
_telegram_app: Optional[Application] = None


async def start_telegram_bot() -> None:
    """Start polling for button callbacks. Safe to call once at server boot."""
    global _telegram_app
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        log.info("TELEGRAM_BOT_TOKEN not set – bot polling disabled")
        return
    if _telegram_app is not None:
        return

    _telegram_app = Application.builder().token(token).build()
    _telegram_app.add_handler(CallbackQueryHandler(on_button_click))
    await _telegram_app.initialize()
    await _telegram_app.start()
    await _telegram_app.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram bot polling started")


async def stop_telegram_bot() -> None:
    global _telegram_app
    if _telegram_app is None:
        return
    try:
        if _telegram_app.updater:
            await _telegram_app.updater.stop()
        await _telegram_app.stop()
        await _telegram_app.shutdown()
    except Exception as e:
        log.warning(f"Telegram shutdown: {e}")
    _telegram_app = None

# STEP 4 – داشبورد Streamlit

## استقرار روی Streamlit Community Cloud (رایگان)

1. بروید به: https://share.streamlit.io
2. با GitHub وارد شوید
3. **New app**
4. ریپوی `airdrop-hunter` را انتخاب کنید
5. **Main file path:** `app.py`
6. Branch: `main`
7. **Advanced settings → Secrets** این را بگذارید:

```toml
DATABASE_URL = "postgresql://...همان آدرس Neon..."
```

8. Deploy

بعد از یک دقیقه آدرس داشبورد چیزی شبیه این می‌شود:
https://airdrop-hunter-xxxx.streamlit.app

## نکات
- داشبورد فقط خواندنی است
- همان دیتابیس Neon ربات را می‌خواند
- فیلتر استراتژی در سایدبار است (پیش‌فرض: بدون تراکنش)

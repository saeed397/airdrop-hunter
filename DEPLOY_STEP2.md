# STEP 2 – استقرار ۲۴/۷ روی Render

## پیش‌نیازها
- حساب Render (رایگان)
- حساب GitHub
- یک Postgres رایگان از **Neon** یا **Supabase**

---

## ۱. ساخت دیتابیس Postgres (Neon – پیشنهادی)

1. بروید به https://neon.tech و ثبت‌نام کنید  
2. یک پروژه جدید بسازید  
3. Connection string را کپی کنید (شبیه این):

```
postgresql://user:password@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

این همان `DATABASE_URL` است.

---

## ۲. پوش کردن کد به GitHub

```bash
cd airdrop_hunter
git init
git add .
git commit -m "Step 2: Render hosting + health + scheduler"
# ریپو را در GitHub بسازید و:
git remote add origin https://github.com/YOUR_USER/airdrop-hunter.git
git branch -M main
git push -u origin main
```

**مهم:** فایل `.env` را هرگز commit نکنید (در `.gitignore` بگذارید).

---

## ۳. ساخت Web Service در Render

### روش A – با Blueprint (ساده‌تر)
1. Render Dashboard → **New** → **Blueprint**
2. ریپوی GitHub را انتخاب کنید
3. `render.yaml` خودکار خوانده می‌شود
4. مقادیر مخفی را پر کنید (حداقل `DATABASE_URL`)

### روش B – دستی
1. **New** → **Web Service**
2. ریپو را وصل کنید
3. تنظیمات:
   - **Runtime:** Docker
   - **Instance type:** Free
   - **Region:** Frankfurt (یا نزدیک‌ترین)
   - **Health Check Path:** `/health`
4. Environment Variables:

| Key | Value |
|-----|-------|
| `DATABASE_URL` | همان connection string از Neon/Supabase |
| `ENVIRONMENT` | `production` |
| `LOG_LEVEL` | `INFO` |
| `SCAN_INTERVAL_MINUTES` | `30` |
| `ALERT_SCORE_THRESHOLD` | `60` |

5. **Create Web Service**

بعد از build موفق، آدرس سرویس چیزی شبیه این است:  
`https://airdrop-hunter-xxxx.onrender.com`

---

## ۴. بیدار نگه‌داشتن سرویس رایگان (UptimeRobot)

پلن رایگان Render بعد از ~۱۵ دقیقه بدون ترافیک **می‌خوابد**.

1. ثبت‌نام در https://uptimerobot.com (رایگان)
2. **Add New Monitor**:
   - Monitor Type: **HTTP(s)**
   - URL: `https://YOUR-SERVICE.onrender.com/health`
   - Interval: **۵ یا ۱۰ دقیقه**
3. ذخیره کنید

با این کار هر ۱۰ دقیقه یک پینگ می‌آید و سرویس بیدار می‌ماند.

---

## ۵. تست بعد از دیپلوی

```bash
# وضعیت سلامت
curl https://YOUR-SERVICE.onrender.com/health

# اجرای دستی یک اسکن (اختیاری)
curl -X POST https://YOUR-SERVICE.onrender.com/scan/now
```

پاسخ `/health` باید `"status": "ok"` و `"scheduler_running": true` باشد.

---

## محدودیت‌های پلن رایگان Render

| مورد | مقدار | نکته |
|------|--------|------|
| ساعت ماهانه | ۷۵۰ ساعت | برای یک سرویس کافی است (~۱ ماه کامل) |
| خوابیدن | بعد از ۱۵ دقیقه بدون ترافیک | با UptimeRobot حل می‌شود |
| دیسک | موقتی (ephemeral) | **هرگز** از SQLite استفاده نکنید → Postgres خارجی |
| RAM | ۵۱۲ MB | برای این ربات کافی است |
| Build | محدود | اگر build طولانی شد، کش Docker کمک می‌کند |

---

## اجرای محلی با Docker (اختیاری)

```bash
cd airdrop_hunter
cp .env.example .env   # DATABASE_URL را پر کنید

docker build -t airdrop-hunter .
docker run --rm -p 10000:10000 --env-file .env airdrop-hunter

# تست
curl http://localhost:10000/health
```

---

## عیب‌یابی سریع

| مشکل | راه‌حل |
|------|--------|
| Build failed – psycopg2 | در Dockerfile پکیج `libpq-dev` هست؛ اگر خطا ماند لاگ build را بفرستید |
| `/health` = 502 | سرویس هنوز boot نشده؛ ۱–۲ دقیقه صبر کنید |
| DB connection error | `DATABASE_URL` را با `?sslmode=require` چک کنید (Neon) |
| Scheduler اجرا نمی‌شود | لاگ Render را ببینید؛ `SCAN_INTERVAL_MINUTES` حداقل ۵ باشد |

---

## مرحله بعد
بعد از تأیید شما → **STEP 3: تلگرام آلرت**

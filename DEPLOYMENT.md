# 🚀 دليل نشر وتشغيل Fel7o Media Pro

يوضح هذا الدليل كيفية تشغيل البوت محلياً أو رفعه على سيرفر VPS. للتشغيل المجاني المستمر راجع `DEPLOY_ORACLE_FREE.md`.

---

## 1. التشغيل المحلي (Local Execution)
1. تأكد من تثبيت بايثون (Python 3.10+) وتثبيت `ffmpeg` على جهازك وإضافته لـ Environment Variables.
2. افتح مجلد المشروع وثبت الاعتمادات:
   ```bash
   pip install -r requirements.txt
   ```
3. قم بإنشاء ملف `.env` وقم بتعبئة التوكنات:
   ```env
   BOT_TOKEN=your_telegram_bot_token
   BOT_USERNAME=your_bot_username
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   SPOTIFY_REDIRECT_URI=http://127.0.0.1:9876/callback
   ADMIN_CHAT_ID=رقم_آي دي_التليجرام_الخاص_بك
   ```
4. شغّل البوت:
   ```bash
   python main.py
   ```

---

## 2. النشر على Oracle Cloud Free (الموصى به)
اتبع `DEPLOY_ORACLE_FREE.md`. يحتوي المشروع على `deploy/oracle/install.sh` وخدمة `systemd` جاهزة لإبقاء البوت يعمل تلقائياً بعد إعادة تشغيل السيرفر.

---

## 3. النشر على Render.com
1. ارفع مشروعك على مستودع خاص أو عام على GitHub.
2. اذهب إلى [Render Dashboard](https://dashboard.render.com/) واضغط على **New +** ثم **Background Worker** (أو Web Service).
3. اربط مستودع GitHub الخاص بك.
4. املأ الإعدادات التالية:
   * **Name:** `fel7o-media-pro`
   * **Runtime:** `Python 3`
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `python main.py`
5. أضف متغيرات البيئة (Environment Variables) في لوحة تحكم Render بنفس أسماء ملف `.env`:
   * `BOT_TOKEN`
   * `SPOTIFY_CLIENT_ID`
   * `SPOTIFY_CLIENT_SECRET`
   * `ADMIN_CHAT_ID`
6. اضغط **Create Background Worker** وسيعمل البوت 24/7!

---

## 4. النشر على Heroku
1. ثبت Heroku CLI وسجل الدخول: `heroku login`
2. أنشئ تطبيقاً جديداً:
   ```bash
   heroku create fel7o-media-pro
   ```
3. أضف حزم البايثون و FFMpeg:
   ```bash
   heroku buildpacks:add heroku/python
   heroku buildpacks:add https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git
   ```
4. ارفع المتغيرات السرية:
   ```bash
   heroku config:set BOT_TOKEN=your_token
   heroku config:set SPOTIFY_CLIENT_ID=your_id
   heroku config:set SPOTIFY_CLIENT_SECRET=your_secret
   heroku config:set ADMIN_CHAT_ID=your_id
   ```
5. انشر الكود:
   ```bash
   git push heroku main
   heroku ps:scale worker=1
   ```

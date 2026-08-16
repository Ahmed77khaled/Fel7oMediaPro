# دليل تشغيل ونشر Fel7o Media

هذا المشروع يستخدم GitHub لحفظ الكود ومراجعة التغييرات فقط. لا تستخدم GitHub Actions كسيرفر 24/7؛ ملف `.github/workflows/bot.yml` يشغّل فحوصات البناء ولا يشغّل البوت باستمرار.

## التشغيل المحلي

ثبّت Python 3.10 أو أحدث، و`ffmpeg`، ثم ثبّت الاعتمادات:

```bash
pip install -r requirements.txt
```

انسخ `.env.example` إلى `.env` وضع **توكنًا جديدًا** أصدرته من BotFather بعد إلغاء أي توكن ظهر في المستودع أو المحادثة. لا تضع `.env` في GitHub.

```env
BOT_TOKEN=your_new_telegram_bot_token
BOT_USERNAME=your_bot_username
ADMIN_CHAT_ID=0
DEFAULT_BITRATE=320
```

شغّل التطبيق محليًا عبر polling:

```bash
python main.py
```

## النشر المجاني على Render Web Service

ملف `render.yaml` يجهز Docker Web Service بخطة `free` وHealth Check على `/health`. أنشئ Web Service من المستودع، أو استخدم Blueprint، ثم أضف الأسرار من لوحة Render بدل كتابتها في الملفات.

| المتغير | القيمة المطلوبة |
|---|---|
| `BOT_TOKEN` | توكن Telegram الجديد فقط |
| `BOT_USERNAME` | اسم البوت دون `@` |
| `WEBHOOK_URL` | رابط الخدمة العام، مثل `https://your-service.onrender.com`، دون `/telegram`؛ التطبيق يضيف المسار تلقائيًا |
| `WEBHOOK_SECRET` | قيمة عشوائية طويلة لا تُشارك علنًا |
| `ADMIN_CHAT_ID` | رقم حساب الإدارة، أو `0` لتعطيل أوامر الإدارة |
| `DEFAULT_BITRATE` | `128` أو `320` أو `flac` |
| `SPOTIFY_CLIENT_ID` و`SPOTIFY_CLIENT_SECRET` | اختياريان لخصائص Spotify فقط |

عند وجود `WEBHOOK_URL` يعمل التطبيق بوضع Webhook ولا يشغّل polling. عند تركه فارغًا يعمل polling، وهو مناسب للتجربة المحلية. يجب اختبار `/health` أولًا، ثم إرسال `/start` للبوت.

> الخطة المجانية لبعض الخدمات المُدارة قد تدخل في وضع السكون أو تفرض حدودًا على CPU والتخزين وحجم الملفات. لذلك فهي مناسبة للتجربة والاستخدام الخفيف، وليست ضمانًا لتشغيل 24/7 أو لتنزيلات كبيرة بلا حدود.

## النشر على Oracle Cloud Free أو VPS

للتشغيل المستمر مع polling وSpotify monitor، استخدم `DEPLOY_ORACLE_FREE.md` أو خدمة VPS تملكها. احفظ الأسرار في متغيرات البيئة، وشغّل `python main.py` عبر systemd أو Docker. لا تستخدم القيم الافتراضية القديمة في أي ملف.

## فحص قبل النشر

نفّذ الأوامر التالية من جذر المشروع:

```bash
python3 -m compileall -q .
python3 tests/test_security_and_formatting.py
git diff --check
```

إذا ظهر أي توكن في تاريخ Git، فإلغاؤه وتدويره يظل ضروريًا حتى بعد حذف القيمة من آخر commit؛ حذف السجل القديم يحتاج عملية تنظيف تاريخ وforce-push منفصلة بعد أخذ نسخة احتياطية.

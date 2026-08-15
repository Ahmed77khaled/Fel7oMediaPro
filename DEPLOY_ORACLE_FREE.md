# تشغيل Fel7o Media Pro على Oracle Free

## ما تحتاجه منك

1. أنشئ حساباً في [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) وأكمل التحقق بنفسك.
2. أنشئ VM بنظام **Ubuntu 24.04** في الـHome Region. اختر Always Free إن ظهر؛ `2 OCPU / 4 GB RAM` مناسب للبوت.
3. احفظ المفتاح الخاص للـSSH، ثم أرسل لي عنوان الـIP العام فقط عندما تصبح الـVM جاهزة. لا ترسل كلمة مرور أو مفاتيح أو توكن البوت داخل الشات.

## الإعداد على السيرفر

بعد رفع المشروع إلى `/opt/fel7o-media-pro`، أنشئ ملف الإعدادات على السيرفر من المثال:

```bash
cd /opt/fel7o-media-pro
cp .env.example .env
nano .env
```

ضع بيانات البوت في `.env`، ثم شغّل:

```bash
sudo bash deploy/oracle/install.sh
```

## الفحص والصيانة

```bash
sudo systemctl status fel7o-media-pro
sudo journalctl -u fel7o-media-pro -f
sudo systemctl restart fel7o-media-pro
```

البوت يستخدم Long Polling، لذلك لا يحتاج فتح منفذ عام له. افتح منفذ SSH فقط لتستطيع إدارة السيرفر.

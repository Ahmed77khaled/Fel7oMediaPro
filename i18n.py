# -*- coding: utf-8 -*-

TRANSLATIONS = {
    "ar": {
        "welcome": (
            "🎧 *Fel7o Media Pro*\n"
            "أرسل رابط Spotify أو YouTube، أو ابحث عن أغنية من الأزرار.\n\n"
            "في الخاص والجروب: احفظ ما يعجبك في مكتبة Fel7o ثم حمّله وقتما تريد."
        ),
        "btn_search_track": "بحث أغاني",
        "btn_search_album": "بحث ألبومات",
        "btn_search_playlist": "قوائم تشغيل",
        "btn_search_artist": "بحث فنانين",
        "btn_search_label": "شركات إنتاج",
        "btn_global_search": "بحث شامل",
        "btn_inbox": "مكتبتي",
        "btn_spotify": "🟢 مزامنة سبوتيفاي",
        "btn_settings": "⚙️ الإعدادات",
        "btn_help": "ℹ️ المساعدة",
        "btn_lang": "🌐 اللغة / English",
        "btn_back": "🔙 رجوع",
        "spotify_connected": "✅ حساب Spotify مرتبط بنجاح!\nاربط Playlist من الزر التالي لمراقبة أغاني Fel7o Inbox الجديدة.",
        "spotify_not_connected": (
            "🔗 *ربط حساب Spotify*\n\n"
            "اضغط على الزر أدناه لتسجيل الدخول، ثم اربط Playlist لمتابعة أغانيها تلقائياً.\n\n"
            "ℹ️ **ملاحظة:** إذا ظهرت لك صفحة خطأ (مثل `localhost`), انسخ رابط الصفحة وأرسله هنا في الشات."
        ),
        "btn_login_spotify": "🟢 تسجيل الدخول بـ Spotify",
        "btn_disconnect_spotify": "🔴 إلغاء ربط Spotify",
        "settings_title": "⚙️ إعدادات البوت والتحميل",
        "quality_title": "🎚 جودة التحميل الحالية: *{q}*",
        "lang_changed": "✅ تم تغيير اللغة إلى العربية بنجاح.",
        "help": "ℹ️ *المساعدة*\n\n• أرسل رابط Spotify أو YouTube إلى البوت أو الجروب.\n• اختر تحميل أو حفظ من بطاقة Fel7o Inbox.\n• استخدم `/inbox` لعرض الأغاني المحفوظة.\n• من الإعدادات اختر جودة الصوت المناسبة.",
        "downloading_steps": [
            "🔍 جاري البحث وتجهيز المسار...",
            "⏳ جاري التنزيل والمعالجة الصوتية...",
            "🎨 جاري دمج الميتاداتا وغلاف الألبوم...",
            "🚀 جاري الرفع إلى تليجرام..."
        ]
    },
    "en": {
        "welcome": (
            "🎧 *Fel7o Media Pro*\n"
            "Download audio or video from a direct link, or search within Telegram.\n\n"
            "Send a YouTube, Spotify, or SoundCloud link to begin, or choose an option below."
        ),
        "btn_search_track": "🎵 Search Track",
        "btn_search_album": "💿 Search Album",
        "btn_search_playlist": "📁 Search Playlist",
        "btn_search_artist": "👤 Search Artist",
        "btn_search_label": "🏷️ Search Label",
        "btn_global_search": "🌐 Global Search",
        "btn_inbox": "❤️ My Library",
        "btn_spotify": "🟢 Spotify Sync",
        "btn_settings": "⚙️ Settings",
        "btn_help": "ℹ️ Help",
        "btn_lang": "🌐 Language / العربية",
        "btn_back": "🔙 Back",
        "spotify_connected": "✅ Spotify account successfully connected!\nUse the next button to link a Playlist and monitor its new tracks.",
        "spotify_not_connected": (
            "🔗 *Connect Spotify Account*\n\n"
            "Tap the button below to log in, then link a Playlist to monitor it automatically.\n\n"
            "ℹ️ **Note:** If the login page fails with a `localhost` error, copy the page URL and paste it here in the chat."
        ),
        "btn_login_spotify": "🟢 Login with Spotify",
        "btn_disconnect_spotify": "🔴 Disconnect Spotify",
        "settings_title": "⚙️ Bot & Download Settings",
        "quality_title": "🎚 Current Download Quality: *{q}*",
        "lang_changed": "✅ Language successfully changed to English.",
        "help": "ℹ️ *Help*\n\n• Send a direct link to download it.\n• Use the search buttons to find content within Telegram.\n• Pick your audio quality in Settings.\n• Spotify is optional and needs your own app settings.",
        "downloading_steps": [
            "🔍 Searching and preparing track...",
            "⏳ Downloading and processing audio...",
            "🎨 Embedding metadata and cover art...",
            "🚀 Uploading to Telegram..."
        ]
    }
}

def get_text(lang: str, key: str, **kwargs) -> str:
    lang_dict = TRANSLATIONS.get(lang, TRANSLATIONS["ar"])
    text = lang_dict.get(key, TRANSLATIONS["ar"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text

import sys
import os
import time
import json
import secrets
import threading
import http.server
import socketserver
import telebot
from telebot import types

if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
import search_engine
import downloader
import spotify_auth
import i18n
from download_queue import DownloadQueue

bot             = telebot.TeleBot(config.BOT_TOKEN, parse_mode="Markdown")
sp_callback_srv = spotify_auth.SpotifyCallbackServer(bot, port=9876)
sp_poller       = spotify_auth.SpotifyPoller(bot, interval=config.SPOTIFY_POLL_INTERVAL_SECONDS)
download_queue  = DownloadQueue(worker_count=2)
download_queue.start()

SETTINGS_FILE = os.path.join(config.DATA_DIR, "user_settings.json")
TRACKS_MAP    = os.path.join(config.DATA_DIR, "tracks_map.json")
GROUP_FAVORITES_FILE = os.path.join(config.DATA_DIR, "group_favorites.json")
RECENT_DOWNLOADS_FILE = os.path.join(config.DATA_DIR, "recent_downloads.json")
ADMIN_FILE    = os.path.join(config.DATA_DIR, "admin_config.json")
INLINE_CACHE_FILE = os.path.join(config.DATA_DIR, "inline_requests.json")
INLINE_CACHE_TTL_SECONDS = 24 * 60 * 60
BATCH_CACHE_FILE = os.path.join(config.DATA_DIR, "download_batches.json")
BATCH_CACHE_TTL_SECONDS = 60 * 60
BATCH_TRACK_LIMIT = 25
SEARCH_CACHE_TTL_SECONDS = 5 * 60
SEARCH_CACHE_MAX_ENTRIES = 64

BOT_USERNAME  = config.BOT_USERNAME or "Fel7oMediaPro"
INLINE_CACHE_LOCK = threading.Lock()
BATCH_CACHE_LOCK = threading.Lock()
BATCH_RUNNING = set()
BATCH_QUEUE_JOBS = {}
SEARCH_CACHE_LOCK = threading.Lock()
SEARCH_CACHE = {}


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def store_inline_request(item):
    now = int(time.time())
    with INLINE_CACHE_LOCK:
        requests = load_json(INLINE_CACHE_FILE, {})
        requests = {
            request_id: request
            for request_id, request in requests.items()
            if now - request.get("created_at", 0) < INLINE_CACHE_TTL_SECONDS
        }
        request_id = secrets.token_urlsafe(6)
        requests[request_id] = {"created_at": now, "item": item}
        save_json(INLINE_CACHE_FILE, requests)
    return request_id


def get_inline_request(request_id):
    with INLINE_CACHE_LOCK:
        request = load_json(INLINE_CACHE_FILE, {}).get(request_id)
    if not request or int(time.time()) - request.get("created_at", 0) >= INLINE_CACHE_TTL_SECONDS:
        return None
    return request.get("item")


def store_download_batch(chat_id, source_url, tracks):
    now = int(time.time())
    with BATCH_CACHE_LOCK:
        batches = load_json(BATCH_CACHE_FILE, {})
        batches = {
            batch_id: batch
            for batch_id, batch in batches.items()
            if now - batch.get("created_at", 0) < BATCH_CACHE_TTL_SECONDS
        }
        batch_id = secrets.token_urlsafe(6)
        batches[batch_id] = {
            "chat_id": chat_id,
            "created_at": now,
            "source_url": source_url,
            "tracks": tracks[:BATCH_TRACK_LIMIT],
        }
        save_json(BATCH_CACHE_FILE, batches)
    return batch_id


def get_download_batch(chat_id, batch_id):
    with BATCH_CACHE_LOCK:
        batch = load_json(BATCH_CACHE_FILE, {}).get(batch_id)
    if not batch or batch.get("chat_id") != chat_id:
        return None
    if int(time.time()) - batch.get("created_at", 0) >= BATCH_CACHE_TTL_SECONDS:
        return None
    return batch


def remove_download_batch(batch_id):
    with BATCH_CACHE_LOCK:
        batches = load_json(BATCH_CACHE_FILE, {})
        if batch_id in batches:
            del batches[batch_id]
            save_json(BATCH_CACHE_FILE, batches)


def get_cached_search_results(query, mode, required_results):
    cache_key = (mode, query.casefold())
    now = time.monotonic()
    with SEARCH_CACHE_LOCK:
        cached = SEARCH_CACHE.get(cache_key)
        if cached and now - cached["stored_at"] < SEARCH_CACHE_TTL_SECONDS and len(cached["results"]) >= required_results:
            return cached["results"]

    results = search_engine.search_tracks(query, limit=required_results, mode=mode)
    with SEARCH_CACHE_LOCK:
        SEARCH_CACHE[cache_key] = {"stored_at": now, "results": results}
        if len(SEARCH_CACHE) > SEARCH_CACHE_MAX_ENTRIES:
            oldest_key = min(SEARCH_CACHE, key=lambda key: SEARCH_CACHE[key]["stored_at"])
            del SEARCH_CACHE[oldest_key]
    return results

def get_user_lang(chat_id):
    return load_json(SETTINGS_FILE, {}).get(str(chat_id), {}).get("lang", "ar")

def set_user_lang(chat_id, lang):
    s = load_json(SETTINGS_FILE, {})
    s.setdefault(str(chat_id), {})["lang"] = lang
    save_json(SETTINGS_FILE, s)

def get_q(chat_id):
    return load_json(SETTINGS_FILE, {}).get(str(chat_id), {}).get("quality", config.DEFAULT_BITRATE)

def set_q(chat_id, quality):
    s = load_json(SETTINGS_FILE, {})
    s.setdefault(str(chat_id), {})["quality"] = quality
    save_json(SETTINGS_FILE, s)

def q_label(q):
    return {"320": "320kbps MP3", "flac": "FLAC — أعلى جودة متاحة", "128": "128kbps"}.get(q, q)


def spotify_status_text(chat_id):
    if not config.SPOTIFY_MONITOR_ENABLED:
        return "🟢 Spotify: متابعة تلقائية موقفة — استخدم Fel7o Inbox داخل الجروب."
    if not spotify_auth.is_connected(chat_id):
        return "🟢 Spotify: غير مرتبط"
    monitor = spotify_auth.get_monitor_status(chat_id)
    labels = {
        "ready": "تعمل",
        "premium_required": "تحتاج Premium",
        "connection_error": "سيعاد الاتصال لاحقًا",
        "not_checked": "بانتظار أول فحص",
    }
    playlist_note = "\n📁 Playlist: مرتبطة" if monitor.get("playlist_url") else "\n📁 Playlist: لم تُضبط بعد"
    return (
        f"🟢 Spotify: *{labels.get(monitor['status'], 'تحت المراجعة')}*\n"
        f"🕒 آخر فحص: `{monitor['last_checked_at']}`\n"
        f"ℹ️ {monitor['detail']}"
        f"{playlist_note}"
    )

def get_admin_id():
    if config.ADMIN_CHAT_ID:
        return config.ADMIN_CHAT_ID
    return load_json(ADMIN_FILE, {}).get("admin_id", 0)

def is_admin(chat_id):
    return chat_id == get_admin_id()

def patch_spotify():
    spotify_auth.SPOTIFY_CLIENT_ID     = config.SPOTIFY_CLIENT_ID
    spotify_auth.SPOTIFY_CLIENT_SECRET = config.SPOTIFY_CLIENT_SECRET

def get_main_menu_markup(lang="ar"):
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(
        types.InlineKeyboardButton("🎵 " + i18n.get_text(lang, "btn_search_track"), switch_inline_query_current_chat=" "),
        types.InlineKeyboardButton("💿 " + i18n.get_text(lang, "btn_search_album"), switch_inline_query_current_chat=".alb "),
        types.InlineKeyboardButton("📋 " + i18n.get_text(lang, "btn_search_playlist"), switch_inline_query_current_chat=".pl "),
        types.InlineKeyboardButton("👤 " + i18n.get_text(lang, "btn_search_artist"), switch_inline_query_current_chat=".art "),
    )
    mk.add(types.InlineKeyboardButton("🏷️ " + i18n.get_text(lang, "btn_search_label"), switch_inline_query_current_chat=".lbl "))
    mk.add(types.InlineKeyboardButton("🌐 " + i18n.get_text(lang, "btn_global_search"), switch_inline_query_current_chat=" "))
    mk.add(
        types.InlineKeyboardButton("❤️ " + i18n.get_text(lang, "btn_inbox"), callback_data="menu_inbox"),
        types.InlineKeyboardButton("🕘 الأخيرة", callback_data="menu_recent"),
    )
    mk.add(
        types.InlineKeyboardButton("⚙️ " + i18n.get_text(lang, "btn_settings"), callback_data="menu_settings"),
    )
    mk.add(
        types.InlineKeyboardButton("ℹ️ " + i18n.get_text(lang, "btn_help"), callback_data="menu_help"),
        types.InlineKeyboardButton("🌐 " + i18n.get_text(lang, "btn_lang"), callback_data="toggle_lang")
    )
    return mk

# ── Handlers ──────────────────────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def h_start(msg):
    chat_id = msg.chat.id
    lang = get_user_lang(chat_id)
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("dl_"):
        item = get_inline_request(parts[1][3:])
        if not item:
            bot.send_message(chat_id, "⌛ انتهت صلاحية نتيجة البحث. ابحث عنها مرة أخرى من القائمة.")
            return
        queue_audio_download(chat_id, item["url"], get_q(chat_id), item["title"])
        return
    text = i18n.get_text(lang, "welcome")
    markup = get_main_menu_markup(lang)
    try:
        bot.send_message(chat_id, "✅ تم تحديث الواجهة.", reply_markup=types.ReplyKeyboardRemove())
        bot.send_message(chat_id, text, reply_markup=markup)
    except Exception:
        bot.send_message(chat_id, text)

@bot.message_handler(commands=["help"])
def h_help(msg):
    chat_id = msg.chat.id
    lang = get_user_lang(chat_id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(i18n.get_text(lang, "btn_back"), callback_data="menu_home"))
    bot.send_message(chat_id, i18n.get_text(lang, "help"), reply_markup=markup)

@bot.message_handler(commands=["settings"])
def h_settings(msg):
    chat_id = msg.chat.id
    lang = get_user_lang(chat_id)
    q = get_q(chat_id)
    mk = types.InlineKeyboardMarkup(row_width=3)
    mk.add(
        types.InlineKeyboardButton("💎 FLAC (الأعلى)", callback_data="set_q:flac"),
        types.InlineKeyboardButton("🟢 320k", callback_data="set_q:320"),
        types.InlineKeyboardButton("🟡 128k", callback_data="set_q:128"),
    )
    mk.add(types.InlineKeyboardButton(i18n.get_text(lang, "btn_back"), callback_data="menu_home"))
    text = (
        f"{i18n.get_text(lang, 'settings_title')}\n\n"
        f"{i18n.get_text(lang, 'quality_title', q=q_label(q))}"
    )
    bot.send_message(chat_id, text, reply_markup=mk)

@bot.message_handler(commands=["info"])
def h_info(msg):
    chat_id = msg.chat.id
    text = (
        "🎧 *Fel7o Media Pro v2.0*\n\n"
        "The most powerful media downloader on Telegram.\n"
        "Developed by: Ahmed Khaled\n"
        "Support: @fel7o_support"
    )
    bot.send_message(chat_id, text)

@bot.callback_query_handler(func=lambda c: c.data == "menu_home")
def cb_menu_home(call):
    chat_id = call.message.chat.id
    lang = get_user_lang(chat_id)
    try:
        bot.edit_message_text(
            i18n.get_text(lang, "welcome"),
            chat_id,
            call.message.message_id,
            reply_markup=get_main_menu_markup(lang)
        )
    except Exception:
        bot.send_message(chat_id, i18n.get_text(lang, "welcome"), reply_markup=get_main_menu_markup(lang))

@bot.callback_query_handler(func=lambda c: c.data == "menu_help")
def cb_menu_help(call):
    chat_id = call.message.chat.id
    lang = get_user_lang(chat_id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(i18n.get_text(lang, "btn_back"), callback_data="menu_home"))
    help_text = i18n.get_text(lang, "help")
    try:
        bot.edit_message_text(help_text, chat_id, call.message.message_id, reply_markup=markup)
    except Exception:
        bot.send_message(chat_id, help_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == "toggle_lang")
def cb_toggle_lang(call):
    chat_id = call.message.chat.id
    current_lang = get_user_lang(chat_id)
    new_lang = "en" if current_lang == "ar" else "ar"
    set_user_lang(chat_id, new_lang)
    bot.answer_callback_query(call.id, i18n.get_text(new_lang, "lang_changed"))
    try:
        bot.edit_message_text(
            i18n.get_text(new_lang, "welcome"),
            chat_id,
            call.message.message_id,
            reply_markup=get_main_menu_markup(new_lang)
        )
    except Exception:
        pass

@bot.callback_query_handler(func=lambda c: c.data == "menu_spotify")
def cb_menu_spotify(call):
    patch_spotify()
    chat_id = call.message.chat.id
    lang = get_user_lang(chat_id)
    bot.answer_callback_query(call.id)
    if not config.spotify_is_configured():
        bot.send_message(chat_id, "Spotify is not configured yet. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to .env.")
        return
    
    if spotify_auth.is_connected(chat_id):
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("📁 ربط Playlist للمتابعة", callback_data="sp_watch_playlist"))
        mk.add(types.InlineKeyboardButton(i18n.get_text(lang, "btn_disconnect_spotify"), callback_data="sp_disconnect"))
        mk.add(types.InlineKeyboardButton(i18n.get_text(lang, "btn_back"), callback_data="menu_home"))
        try:
            bot.edit_message_text(i18n.get_text(lang, "spotify_connected"), chat_id, call.message.message_id, reply_markup=mk)
        except Exception:
            bot.send_message(chat_id, i18n.get_text(lang, "spotify_connected"), reply_markup=mk)
    else:
        auth_url = spotify_auth.get_auth_url(chat_id)
        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton(i18n.get_text(lang, "btn_login_spotify"), url=auth_url))
        mk.add(types.InlineKeyboardButton(i18n.get_text(lang, "btn_back"), callback_data="menu_home"))
        try:
            bot.edit_message_text(i18n.get_text(lang, "spotify_not_connected"), chat_id, call.message.message_id, reply_markup=mk)
        except Exception:
            bot.send_message(chat_id, i18n.get_text(lang, "spotify_not_connected"), reply_markup=mk)


@bot.callback_query_handler(func=lambda c: c.data == "sp_watch_playlist")
def cb_watch_playlist(call):
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "أرسل رابط Playlist الخاصة بك بهذا الشكل:\n"
        "`/watch_playlist https://open.spotify.com/playlist/...`\n\n"
        "أول فحص يحفظ الموجود بدون رسائل، وبعدها يصلك تنبيه بالأغاني الجديدة كل 6 ساعات.",
    )


@bot.message_handler(commands=["watch_playlist"])
def h_watch_playlist(msg):
    chat_id = msg.chat.id
    if not spotify_auth.is_connected(chat_id):
        bot.reply_to(msg, "اربط حساب Spotify أولاً من زر Spotify في القائمة.")
        return
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) != 2:
        bot.reply_to(msg, "أرسل الرابط هكذا:\n`/watch_playlist https://open.spotify.com/playlist/...`")
        return
    playlist_url = spotify_auth.set_playlist_watch(chat_id, parts[1].strip())
    if not playlist_url:
        bot.reply_to(msg, "هذا ليس رابط Spotify Playlist صحيحاً.")
        return
    bot.reply_to(
        msg,
        "✅ تم ربط Playlist للمتابعة. أول فحص خلال 6 ساعات ينشئ خط الأساس بدون رسائل، ثم يتم تنبيهك بالجديد فقط.",
    )

@bot.callback_query_handler(func=lambda c: c.data == "sp_disconnect")
def cb_sp_disconnect(call):
    chat_id = call.message.chat.id
    lang = get_user_lang(chat_id)
    spotify_auth.disconnect(chat_id)
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton(i18n.get_text(lang, "btn_back"), callback_data="menu_home"))
    try:
        bot.edit_message_text("🔴 Spotify disconnected.", chat_id, call.message.message_id, reply_markup=mk)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda c: c.data == "menu_settings")
def cb_menu_settings(call):
    chat_id = call.message.chat.id
    lang = get_user_lang(chat_id)
    q = get_q(chat_id)
    mk = types.InlineKeyboardMarkup(row_width=3)
    mk.add(
        types.InlineKeyboardButton("💎 FLAC (الأعلى)", callback_data="set_q:flac"),
        types.InlineKeyboardButton("🟢 320k", callback_data="set_q:320"),
        types.InlineKeyboardButton("🟡 128k", callback_data="set_q:128"),
    )
    mk.add(types.InlineKeyboardButton(i18n.get_text(lang, "btn_back"), callback_data="menu_home"))
    text = (
        f"{i18n.get_text(lang, 'settings_title')}\n\n"
        f"{i18n.get_text(lang, 'quality_title', q=q_label(q))}"
    )
    try:
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=mk)
    except Exception:
        bot.send_message(chat_id, text, reply_markup=mk)

@bot.callback_query_handler(func=lambda c: c.data.startswith("set_q:"))
def cb_quality(call):
    chat_id = call.message.chat.id
    lang = get_user_lang(chat_id)
    q = call.data.split(":", 1)[1]
    set_q(chat_id, q)
    bot.answer_callback_query(call.id, f"Quality set to {q_label(q)}")
    cb_menu_settings(call)

# ── Download Processing with Progress Bar ─────────────────────────────────────
def send_podcast(chat_id, url, status_msg_id=None):
    lang = get_user_lang(chat_id)
    
    def update_status(msg):
        if status_msg_id:
            try:
                bot.edit_message_text(msg, chat_id, status_msg_id)
            except Exception:
                pass

    update_status("🎙️ Downloading podcast episode...")
    res = downloader.download_podcast(url)
    
    if res.get('status') != 'success':
        update_status(f"❌ Podcast download failed: {res.get('error')}")
        return

    file_path = res['file_path']
    title = res['title']
    duration = res['duration']

    update_status("🚀 Uploading podcast audio...")
    try:
        with open(file_path, 'rb') as audio:
            bot.send_audio(chat_id, audio, caption=f"🎙️ *{title}*\n⚡ Via @{BOT_USERNAME}", title=title, performer="Podcast", duration=duration)
        if status_msg_id:
            bot.delete_message(chat_id, status_msg_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error sending podcast: {e}")

def send_video(chat_id, url, status_msg_id=None):
    lang = get_user_lang(chat_id)
    
    def update_status(msg):
        if status_msg_id:
            try:
                bot.edit_message_text(msg, chat_id, status_msg_id)
            except Exception:
                pass

    update_status("⏳ Downloading video...")
    res = downloader.download_video(url)
    
    if res.get('status') != 'success':
        update_status(f"❌ Video download failed: {res.get('error')}")
        return

    file_path = res['file_path']
    title = res['title']
    duration = res['duration']

    update_status("🚀 Uploading video...")
    try:
        with open(file_path, 'rb') as video:
            bot.send_video(chat_id, video, caption=f"🎬 *{title}*\n⚡ Via @{BOT_USERNAME}", duration=duration)
        if status_msg_id:
            bot.delete_message(chat_id, status_msg_id)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error sending video: {e}")

def send_audio(chat_id, query, quality, status_msg_id=None, spotify_meta=None):
    lang = get_user_lang(chat_id)
    steps = i18n.get_text(lang, "downloading_steps")
    
    def update_status(step_idx):
        if status_msg_id:
            try:
                bot.edit_message_text(steps[step_idx], chat_id, status_msg_id)
            except Exception:
                pass

    update_status(0)
    time.sleep(0.5)
    update_status(1)
    
    res = downloader.download_audio(query, quality=quality, spotify_meta=spotify_meta)
    
    if res.get('status') != 'success':
        err = res.get('error', 'Unknown error')
        if status_msg_id:
            try:
                bot.edit_message_text(f"❌ Download failed: {err}", chat_id, status_msg_id)
            except Exception:
                pass
        else:
            bot.send_message(chat_id, f"❌ Download failed: {err}")
        return False

    update_status(2)
    time.sleep(0.3)
    update_status(3)

    file_path = res['file_path']
    title     = res['title']
    artist    = res['artist']
    duration  = res['duration']
    thumb     = res['thumbnail_path']
    q_used    = res['quality']

    caption = (
        f"🎵 *{title}*\n"
        f"👤 {artist}\n"
        f"🎚 Quality: `{q_label(q_used)}`\n"
        f"⚡ Via @{BOT_USERNAME}"
    )

    try:
        with open(file_path, 'rb') as audio:
            if thumb and os.path.exists(thumb):
                with open(thumb, 'rb') as th:
                    bot.send_audio(
                        chat_id,
                        audio,
                        caption=caption,
                        duration=duration,
                        performer=artist,
                        title=title,
                        thumb=th
                    )
            else:
                bot.send_audio(
                    chat_id,
                    audio,
                    caption=caption,
                    duration=duration,
                    performer=artist,
                    title=title
                )
        if status_msg_id:
            try:
                bot.delete_message(chat_id, status_msg_id)
            except Exception:
                pass
    except Exception as e:
        print(f"[Send Error] {e}")
        bot.send_message(chat_id, f"❌ Error sending file: {e}")
        return False
    record_recent_download(chat_id, title, artist, query)
    return True


def enqueue_download(chat_id, label, action):
    job, position = download_queue.enqueue(chat_id, label, action)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✖️ إلغاء من الانتظار", callback_data=f"queue_cancel:{job.job_id}"))
    bot.send_message(
        chat_id,
        f"⏳ أُضيف *{label[:55]}* إلى قائمة الانتظار. ترتيبك: *{position}*.",
        reply_markup=markup,
    )
    return job


def queue_audio_download(chat_id, query, quality, label="الأغنية"):
    def action():
        status_message = bot.send_message(chat_id, f"⬇️ جاري تجهيز *{label[:70]}* للتحميل...")
        send_audio(chat_id, query, quality, status_message.message_id)

    return enqueue_download(chat_id, label, action)


def queue_podcast_download(chat_id, url):
    def action():
        status_message = bot.send_message(chat_id, "🎙️ جاري تجهيز البودكاست للتحميل...")
        send_podcast(chat_id, url, status_message.message_id)

    return enqueue_download(chat_id, "حلقة بودكاست", action)


def queue_video_download(chat_id, url):
    def action():
        status_message = bot.send_message(chat_id, "🎬 جاري تجهيز الفيديو للتحميل...")
        send_video(chat_id, url, status_message.message_id)

    return enqueue_download(chat_id, "فيديو", action)


@bot.callback_query_handler(func=lambda c: c.data.startswith("queue_cancel:"))
def cb_queue_cancel(call):
    job_id = call.data.split(":", 1)[1]
    outcome = download_queue.cancel(call.message.chat.id, job_id)
    if outcome == "cancelled":
        bot.answer_callback_query(call.id, "تم إلغاء الطلب من قائمة الانتظار.")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
    elif outcome == "active":
        bot.answer_callback_query(call.id, "بدأ التنزيل بالفعل ولا يمكن إيقافه بأمان.", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "هذا الطلب لم يعد في قائمة الانتظار.")

# ── Direct URL and Callback Handlers ──────────────────────────────────────────
STATS_FILE = os.path.join(config.DATA_DIR, "bot_stats.json")

def log_stat(user_id, username, track_title):
    try:
        stats = load_json(STATS_FILE, {"downloads": 0, "users": {}, "history": []})
        stats["downloads"] = stats.get("downloads", 0) + 1
        stats["users"][str(user_id)] = username or "Unknown"
        stats["history"].insert(0, {"user": username, "track": track_title, "time": time.strftime("%Y-%m-%d %H:%M")})
        stats["history"] = stats["history"][:50] # Keep last 50
        save_json(STATS_FILE, stats)
    except Exception as e:
        print(f"[Stats Error] {e}")


def record_recent_download(chat_id, title, artist, url):
    try:
        recent = load_json(RECENT_DOWNLOADS_FILE, {})
        entries = recent.setdefault(str(chat_id), [])
        entries.insert(0, {
            "title": title,
            "artist": artist,
            "url": url,
            "downloaded_at": int(time.time()),
        })
        recent[str(chat_id)] = entries[:25]
        save_json(RECENT_DOWNLOADS_FILE, recent)
    except Exception as error:
        print(f"[Recent downloads error] {error}")


def is_group_chat(message):
    return getattr(message.chat, "type", "private") in {"group", "supergroup"}


def escape_markdown(value):
    return str(value or "").replace("\\", "\\\\").replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]").replace("`", "\\`")


def get_inbox_item(url):
    if "spotify.com" in url:
        info = search_engine.get_spotify_info(url) or {}
        return {
            "title": info.get("title") or "رابط Spotify",
            "artist": info.get("artist") or "Spotify",
            "thumbnail": info.get("thumbnail") or "",
            "url": url,
        }
    return {"title": "رابط موسيقى", "artist": "YouTube أو مصدر آخر", "thumbnail": "", "url": url}


def save_group_favorite(chat_id, item):
    favorites = load_json(GROUP_FAVORITES_FILE, {})
    group_favorites = favorites.setdefault(str(chat_id), [])
    if any(saved.get("url") == item.get("url") for saved in group_favorites):
        return False
    group_favorites.insert(0, {
        "title": item.get("title", "رابط موسيقى"),
        "artist": item.get("artist", ""),
        "url": item.get("url", ""),
        "thumbnail": item.get("thumbnail", ""),
        "saved_at": int(time.time()),
    })
    favorites[str(chat_id)] = group_favorites[:200]
    save_json(GROUP_FAVORITES_FILE, favorites)
    return True


def send_group_inbox_card(message, url):
    item = get_inbox_item(url)
    request_id = store_inline_request(item)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬇️ تحميل", callback_data=f"inbox_dl:{request_id}"),
        types.InlineKeyboardButton("❤️ حفظ", callback_data=f"inbox_save:{request_id}"),
    )
    if is_group_chat(message):
        markup.add(types.InlineKeyboardButton("📩 أرسل لي خاص", callback_data=f"inbox_dm:{request_id}"))
    markup.add(types.InlineKeyboardButton("✖️ تجاهل", callback_data=f"inbox_ignore:{request_id}"))
    caption = (
        f"📥 *Fel7o Inbox*\n\n"
        f"🎵 {escape_markdown(item['title'])}\n"
        f"👤 {escape_markdown(item['artist'])}\n\n"
        f"💎 الجودة: {escape_markdown(q_label(get_q(message.chat.id)))}\n\n"
        "اختر ما تريد عمله بالأغنية."
    )
    try:
        if item.get("thumbnail"):
            bot.send_photo(message.chat.id, item["thumbnail"], caption=caption, reply_markup=markup)
        else:
            bot.reply_to(message, caption, reply_markup=markup)
    except Exception as error:
        print(f"[Inbox card error] {error}")
        bot.reply_to(message, "📥 وصل رابط جديد إلى Fel7o Inbox.", reply_markup=markup)


def send_inbox(chat_id, reply_to=None):
    favorites = load_json(GROUP_FAVORITES_FILE, {}).get(str(chat_id), [])
    if not favorites:
        if reply_to:
            bot.reply_to(reply_to, "لا توجد أغاني محفوظة في مكتبتك حتى الآن.")
        else:
            bot.send_message(chat_id, "لا توجد أغاني محفوظة في مكتبتك حتى الآن.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for item in favorites[:10]:
        request_id = store_inline_request(item)
        label = f"⬇️ {item.get('title', 'أغنية')} — {item.get('artist', '')}"[:62]
        markup.add(types.InlineKeyboardButton(label, callback_data=f"inbox_dl:{request_id}"))
    if reply_to:
        bot.reply_to(reply_to, "❤️ آخر الأغاني المحفوظة في مكتبتك:", reply_markup=markup)
    else:
        bot.send_message(chat_id, "❤️ آخر الأغاني المحفوظة في مكتبتك:", reply_markup=markup)


@bot.message_handler(commands=["inbox"])
def h_inbox(msg):
    send_inbox(msg.chat.id, reply_to=msg)


@bot.callback_query_handler(func=lambda c: c.data == "menu_inbox")
def cb_menu_inbox(call):
    bot.answer_callback_query(call.id)
    send_inbox(call.message.chat.id)


def send_recent_downloads(chat_id, reply_to=None):
    entries = load_json(RECENT_DOWNLOADS_FILE, {}).get(str(chat_id), [])
    if not entries:
        message = "لا توجد تحميلات سابقة هنا حتى الآن."
        if reply_to:
            bot.reply_to(reply_to, message)
        else:
            bot.send_message(chat_id, message)
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for entry in entries[:10]:
        request_id = store_inline_request(entry)
        label = f"🔁 {entry.get('title', 'أغنية')} — {entry.get('artist', '')}"[:62]
        markup.add(types.InlineKeyboardButton(label, callback_data=f"inbox_dl:{request_id}"))
    message = "🕘 آخر التحميلات — اضغط لإعادة التحميل:"
    if reply_to:
        bot.reply_to(reply_to, message, reply_markup=markup)
    else:
        bot.send_message(chat_id, message, reply_markup=markup)


@bot.message_handler(commands=["recent"])
def h_recent_downloads(msg):
    send_recent_downloads(msg.chat.id, reply_to=msg)


@bot.callback_query_handler(func=lambda c: c.data == "menu_recent")
def cb_menu_recent(call):
    bot.answer_callback_query(call.id)
    send_recent_downloads(call.message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("inbox_"))
def cb_group_inbox(call):
    action, request_id = call.data.split(":", 1)
    item = get_inline_request(request_id)
    if not item:
        bot.answer_callback_query(call.id, "انتهت صلاحية البطاقة. أرسل الرابط مرة أخرى.")
        return
    chat_id = call.message.chat.id
    if action == "inbox_dl":
        bot.answer_callback_query(call.id, "أُضيف إلى الانتظار")
        queue_audio_download(chat_id, item["url"], get_q(chat_id), item.get("title", "الأغنية"))
    elif action == "inbox_dm":
        recipient_id = call.from_user.id
        try:
            bot.send_message(recipient_id, "📩 سيتم إرسال التحميل هنا في الخاص.")
        except Exception:
            bot.answer_callback_query(call.id, "افتح البوت في الخاص واضغط /start أولاً.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "سيصلك التحميل في الخاص")
        queue_audio_download(recipient_id, item["url"], get_q(recipient_id), item.get("title", "الأغنية"))
    elif action == "inbox_save":
        saved = save_group_favorite(chat_id, item)
        bot.answer_callback_query(call.id, "تم الحفظ في مفضلة Inbox" if saved else "الأغنية محفوظة بالفعل")
    elif action == "inbox_ignore":
        bot.answer_callback_query(call.id, "تم التجاهل")
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass

@bot.message_handler(commands=["stats"])
def h_stats(msg):
    chat_id = msg.chat.id
    if not is_admin(chat_id) and config.ADMIN_CHAT_ID != 0:
        bot.reply_to(msg, "❌ عذراً، هذا الأمر مخصص للمسؤول فقط.")
        return
    stats = load_json(STATS_FILE, {"downloads": 0, "users": {}, "history": []})
    total_downloads = stats.get("downloads", 0)
    total_users = len(stats.get("users", {}))
    history = stats.get("history", [])
    
    text = (
        f"📊 *لوحة إحصائيات البوت (Admin Stats)*\n\n"
        f"📥 إجمالي التحميلات: `{total_downloads}`\n"
        f"👥 إجمالي المستخدمين الفريدين: `{total_users}`\n\n"
        f"🕒 *آخر 5 تحميلات:*\n"
    )
    for h in history[:5]:
        text += f"• `{h['track']}` (بواسطة @{h['user']})\n"
    
    bot.send_message(chat_id, text)

@bot.message_handler(func=lambda msg: msg.text and ("http://" in msg.text or "https://" in msg.text))
def h_url(msg):
    chat_id = msg.chat.id
    url = msg.text.strip()
    q = get_q(chat_id)
    lang = get_user_lang(chat_id)

    is_single_music_link = any(marker in url for marker in (
        "open.spotify.com/track/", "youtube.com/watch", "youtu.be/", "music.youtube.com/",
        "soundcloud.com/",
    ))
    if is_group_chat(msg) or is_single_music_link:
        send_group_inbox_card(msg, url)
        return
    
    # Check if Podcast (Spotify Episode or Podcast link)
    if "episode" in url or "show" in url or "podcasts.apple.com" in url:
        log_stat(chat_id, msg.from_user.username, "Podcast: " + url)
        queue_podcast_download(chat_id, url)
        return

    # Check if Video (Reels, Shorts, TikTok)
    video_platforms = ["instagram.com/reels", "instagram.com/reel", "tiktok.com", "youtube.com/shorts"]
    if any(p in url for p in video_platforms):
        log_stat(chat_id, msg.from_user.username, "Video: " + url)
        queue_video_download(chat_id, url)
        return

    # Check if playlist
    if "playlist" in url or "list=" in url or "album" in url:
        bot.send_message(chat_id, "📁 تم اكتشاف ألبوم أو قائمة تشغيل. جاري تجهيز الخيارات...")
        tracks = search_engine.get_playlist_tracks(url, limit=BATCH_TRACK_LIMIT)
        if not tracks:
            bot.send_message(chat_id, "❌ لم يتم العثور على أغاني داخل القائمة أو رابط غير صالح.")
            return
        batch_id = store_download_batch(chat_id, url, tracks)
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬇️ تنزيل الكل", callback_data=f"batch_all:{batch_id}"),
            types.InlineKeyboardButton("🎵 اختيار أغاني", callback_data=f"batch_pick:{batch_id}"),
        )
        markup.add(types.InlineKeyboardButton("✖️ إلغاء", callback_data=f"batch_cancel:{batch_id}"))
        bot.send_message(
            chat_id,
            f"📁 تم العثور على *{len(tracks)}* أغنية.\n"
            f"سيتم تنزيل حد أقصى *{BATCH_TRACK_LIMIT}* أغنية بالتتابع.",
            reply_markup=markup,
        )
        return

    log_stat(chat_id, msg.from_user.username, url)
    queue_audio_download(chat_id, url, q, "رابط Spotify أو YouTube")


@bot.message_handler(func=lambda msg: msg.chat.type == "private" and msg.text and not msg.text.startswith("/") and "http://" not in msg.text and "https://" not in msg.text)
def h_text_search(msg):
    query = msg.text.strip()
    if len(query) < 2:
        bot.reply_to(msg, "اكتب حرفين على الأقل للبحث.")
        return

    results = get_cached_search_results(query, "track", required_results=5)
    if not results:
        bot.reply_to(msg, "لم أجد نتائج. جرّب اسمًا مختلفًا.")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for item in results[:5]:
        request_id = store_inline_request({
            "title": item.get("title", "بدون عنوان"),
            "artist": item.get("artist", ""),
            "url": item.get("url", ""),
        })
        title = item.get("title", "بدون عنوان")[:40]
        artist = item.get("artist", "")[:28]
        markup.add(types.InlineKeyboardButton(f"⬇️ {title} — {artist}", callback_data=f"dl_cached:{request_id}"))

    bot.reply_to(msg, f"🔎 نتائج البحث عن *{query}*:", reply_markup=markup)


def run_download_batch(chat_id, batch_id, tracks):
    quality = get_q(chat_id)
    status_message = bot.send_message(chat_id, f"⬇️ بدء تنزيل {len(tracks)} أغنية...")
    completed = 0
    failed = 0
    try:
        for index, track in enumerate(tracks, 1):
            title = track.get("title") or "بدون عنوان"
            query = track.get("url") or f"{track.get('artist', '')} - {title}"
            try:
                bot.edit_message_text(
                    f"⬇️ جاري تنزيل ({index}/{len(tracks)}): *{title}*",
                    chat_id,
                    status_message.message_id,
                )
            except Exception:
                pass
            if send_audio(chat_id, query, quality):
                completed += 1
                log_stat(chat_id, None, title)
            else:
                failed += 1
        bot.edit_message_text(
            f"✅ اكتملت الدفعة.\nنجح: *{completed}*\nفشل: *{failed}*",
            chat_id,
            status_message.message_id,
        )
    finally:
        with BATCH_CACHE_LOCK:
            BATCH_RUNNING.discard(batch_id)
            BATCH_QUEUE_JOBS.pop(batch_id, None)


@bot.callback_query_handler(func=lambda c: c.data.startswith("batch_"))
def cb_download_batch(call):
    chat_id = call.message.chat.id
    parts = call.data.split(":")
    action = parts[0]
    batch_id = parts[1] if len(parts) > 1 else ""
    batch = get_download_batch(chat_id, batch_id)
    if not batch:
        bot.answer_callback_query(call.id, "انتهت صلاحية القائمة. أرسل الرابط مرة أخرى.")
        return

    if action == "batch_cancel":
        remove_download_batch(batch_id)
        with BATCH_CACHE_LOCK:
            queued_job_id = BATCH_QUEUE_JOBS.pop(batch_id, None)
            BATCH_RUNNING.discard(batch_id)
        if queued_job_id:
            download_queue.cancel(chat_id, queued_job_id)
        bot.answer_callback_query(call.id, "تم الإلغاء")
        bot.edit_message_text("✖️ تم إلغاء تنزيل القائمة.", chat_id, call.message.message_id)
        return

    if action == "batch_pick":
        markup = types.InlineKeyboardMarkup(row_width=1)
        for index, track in enumerate(batch["tracks"]):
            title = (track.get("title") or "بدون عنوان")[:42]
            markup.add(types.InlineKeyboardButton(f"{index + 1}. {title}", callback_data=f"batch_track:{batch_id}:{index}"))
        markup.add(types.InlineKeyboardButton("✖️ إلغاء", callback_data=f"batch_cancel:{batch_id}"))
        bot.answer_callback_query(call.id)
        bot.edit_message_text("🎵 اختر أغنية لتنزيلها:", chat_id, call.message.message_id, reply_markup=markup)
        return

    if action == "batch_track":
        track_index = parts[2] if len(parts) > 2 else ""
        if not batch or not track_index.isdigit() or int(track_index) >= len(batch["tracks"]):
            bot.answer_callback_query(call.id, "الأغنية لم تعد متاحة.")
            return
        track = batch["tracks"][int(track_index)]
        query = track.get("url") or f"{track.get('artist', '')} - {track.get('title', '')}"
        bot.answer_callback_query(call.id, "أُضيف إلى الانتظار")
        queue_audio_download(chat_id, query, get_q(chat_id), track.get("title", "الأغنية"))
        return

    if action == "batch_all":
        with BATCH_CACHE_LOCK:
            if batch_id in BATCH_RUNNING:
                bot.answer_callback_query(call.id, "هذه الدفعة تعمل بالفعل.")
                return
            BATCH_RUNNING.add(batch_id)
        bot.answer_callback_query(call.id, "أُضيفت الدفعة إلى الانتظار")
        job = enqueue_download(
            chat_id,
            f"دفعة من {len(batch['tracks'])} أغنية",
            lambda: run_download_batch(chat_id, batch_id, batch["tracks"]),
        )
        with BATCH_CACHE_LOCK:
            BATCH_QUEUE_JOBS[batch_id] = job.job_id

@bot.callback_query_handler(func=lambda c: c.data.startswith("dl_sync:") or c.data.startswith("dl_item:") or c.data.startswith("dl_url:") or c.data.startswith("dl_cached:"))
def cb_download_item(call):
    chat_id = call.message.chat.id
    q = get_q(chat_id)
    data = call.data
    
    if data.startswith("dl_sync:"):
        tid = data.split(":", 1)[1]
        tmap = load_json(TRACKS_MAP, {})
        info = tmap.get(tid)
        if not info:
            bot.answer_callback_query(call.id, "Track info not found.")
            return
        query = info.get("url") or f"{info.get('artist')} - {info.get('title')}"
        bot.answer_callback_query(call.id, "أُضيف إلى الانتظار")
        queue_audio_download(chat_id, query, q, info.get("title", "الأغنية"))
    elif data.startswith("dl_cached:"):
        item = get_inline_request(data.split(":", 1)[1])
        if not item:
            bot.answer_callback_query(call.id, "انتهت صلاحية النتيجة. ابحث مرة أخرى.")
            return
        bot.answer_callback_query(call.id, "أُضيف إلى الانتظار")
        queue_audio_download(chat_id, item["url"], q, item.get("title", "الأغنية"))
    elif data.startswith("dl_url:"):
        url = data.split(":", 1)[1]
        bot.answer_callback_query(call.id, "أُضيف إلى الانتظار")
        queue_audio_download(chat_id, url, q, "رابط مباشر")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ign_sync:"))
def cb_ignore_sync(call):
    bot.answer_callback_query(call.id, "Ignored.")
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

# ── Manual Spotify Auth Handler ───────────────────────────────────────────────
@bot.message_handler(func=lambda msg: msg.text and ("code=" in msg.text and "state=" in msg.text))
def h_manual_spotify_auth(msg):
    chat_id = msg.chat.id
    lang = get_user_lang(chat_id)
    if spotify_auth.process_callback_url(chat_id, msg.text):
        bot.reply_to(msg, "✅ تم ربط حساب Spotify بنجاح عبر الرابط اليدوي!")
        cb_menu_spotify(types.CallbackQuery(id="0", message=msg, data="menu_spotify", from_user=msg.from_user))
    else:
        bot.reply_to(msg, "❌ فشل الربط. تأكد من إرسال الرابط كاملاً.")

# ── Inline Search Handler ─────────────────────────────────────────────────────
@bot.inline_handler(func=lambda q: True)
def inline_search(iq):
    query = iq.query.strip()
    mode = "track"
    if query.startswith(".trk "):
        mode = "track"
        query = query[5:]
    elif query.startswith(".alb "):
        mode = "album"
        query = query[5:]
    elif query.startswith(".pl "):
        mode = "playlist"
        query = query[4:]
    elif query.startswith(".art "):
        mode = "artist"
        query = query[5:]
    elif query.startswith(".lbl "):
        mode = "label"
        query = query[5:]

    if len(query) < 2:
        try:
            bot.answer_inline_query(
                iq.id,
                [],
                cache_time=1,
                switch_pm_text="Open Fel7o Media Pro to search or download",
                switch_pm_parameter="home",
            )
        except telebot.apihelper.ApiTelegramException as error:
            print(f"[Inline] Ignored expired query: {error}")
        return

    page_size = 8
    try:
        page = max(int(iq.offset or "0"), 0)
    except ValueError:
        page = 0
    results = get_cached_search_results(query, mode, required_results=(page + 1) * page_size)
    page_results = results[page * page_size:(page + 1) * page_size]
    articles = []
    mode_labels = {
        "track": "Track",
        "album": "Album search",
        "playlist": "Playlist search",
        "artist": "Artist search",
        "label": "Label search",
    }
    for idx, item in enumerate(page_results):
        title  = item.get('title', 'Unknown')
        artist = item.get('artist', 'Unknown')
        album = item.get('album', 'YouTube Music')
        duration = item.get('duration_str', '03:00')
        thumb  = item.get('thumbnail', '')
        url    = item.get('url', '')

        request_id = store_inline_request({"title": title, "artist": artist, "url": url})
        download_link = f"https://t.me/{BOT_USERNAME}?start=dl_{request_id}"
        desc = f"Artist: {artist}\nAlbum: {album}"
        content = types.InputTextMessageContent(
            f"🎵 *{title}*\n👤 {artist}\n💿 {album}\n⏱ {duration}",
            parse_mode="Markdown",
        )

        mk = types.InlineKeyboardMarkup()
        mk.add(types.InlineKeyboardButton("⬇️ Open bot to download", url=download_link))

        articles.append(
            types.InlineQueryResultArticle(
                id=f"{page}-{idx}-{item.get('id', idx)}",
                title=title,
                description=desc,
                input_message_content=content,
                thumbnail_url=thumb,
                reply_markup=mk
            )
        )
    try:
        bot.answer_inline_query(
            iq.id,
            articles,
            cache_time=10,
            next_offset=str(page + 1) if len(page_results) == page_size else "",
        )
    except telebot.apihelper.ApiTelegramException as error:
        print(f"[Inline] Ignored expired query: {error}")

def start_health_check_server():
    port = int(os.environ.get("PORT", "8000"))
    class HealthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Fel7o Media Pro is running 24/7!")

        def log_message(self, format, *args):
            return  # Suppress noisy logs

    def _serve():
        try:
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("0.0.0.0", port), HealthHandler) as httpd:
                print(f"[HealthCheck] Server listening on 0.0.0.0:{port}")
                httpd.serve_forever()
        except Exception as err:
            print(f"[HealthCheck] Notice: {err}")

    threading.Thread(target=_serve, daemon=True, name="HealthCheckServer").start()

# ── Startup ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[Fel7o Media Pro] Starting...")
    config.validate_runtime_config()
    patch_spotify()
    start_health_check_server()
    
    try:
        bot.set_my_commands([
            types.BotCommand("start", "Start the bot"),
            types.BotCommand("help", "How to use the bot"),
            types.BotCommand("settings", "Change your preferences"),
            types.BotCommand("inbox", "Open saved songs"),
            types.BotCommand("recent", "Open recent downloads"),
            types.BotCommand("stats", "Bot download statistics (Admin)"),
            types.BotCommand("info", "Get some useful information about the bot")
        ])
        bot_info = bot.get_me()
        BOT_USERNAME = bot_info.username or BOT_USERNAME
    except Exception as e:
        print(f"[Menu Error] {e}")

    if config.spotify_is_configured():
        sp_callback_srv.start()
        if config.SPOTIFY_MONITOR_ENABLED:
            sp_poller.start()
    print("[Fel7o Media Pro] Ready! Bot: @" + BOT_USERNAME)
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print("[polling error]", e)
            time.sleep(5)


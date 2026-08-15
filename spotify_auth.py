import os
import json
import time
import threading
import http.server
import socketserver
import urllib.parse
import re

import spotipy
from spotipy.oauth2 import SpotifyOAuth

import config

# ─── Paths ───────────────────────────────────────────────────────────────────
DATA_DIR        = config.DATA_DIR
USERS_FILE      = os.path.join(DATA_DIR, "spotify_users.json")
HISTORY_FILE    = os.path.join(DATA_DIR, "spotify_history.json")
TRACKS_MAP_FILE = os.path.join(DATA_DIR, "tracks_map.json")

# ─── Spotify App Credentials ──────────────────────────────────────────────────
SPOTIFY_CLIENT_ID     = config.SPOTIFY_CLIENT_ID
SPOTIFY_CLIENT_SECRET = config.SPOTIFY_CLIENT_SECRET
REDIRECT_URI          = config.SPOTIFY_REDIRECT_URI
SCOPE                 = "user-library-read playlist-read-private"

os.makedirs(DATA_DIR, exist_ok=True)

# ─── JSON helpers ─────────────────────────────────────────────────────────────
def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── Per-user token cache path ────────────────────────────────────────────────
def token_cache_path(chat_id: int) -> str:
    return os.path.join(DATA_DIR, f"sp_token_{chat_id}.json")

# ─── Per-user OAuth manager ──────────────────────────────────────────────────
def get_oauth(chat_id: int) -> SpotifyOAuth:
    return SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=token_cache_path(chat_id),
        open_browser=False,
        show_dialog=True,
    )

# ─── Generate auth URL per user (state = chat_id) ─────────────────────────────
def get_auth_url(chat_id: int) -> str:
    oauth = get_oauth(chat_id)
    return oauth.get_authorize_url(state=str(chat_id))

# ─── Spotify client for authenticated user ────────────────────────────────────
def get_sp_client(chat_id: int):
    oauth = get_oauth(chat_id)
    token = oauth.get_cached_token()
    if not token:
        return None
    try:
        if oauth.is_token_expired(token):
            token = oauth.refresh_access_token(token["refresh_token"])
        return spotipy.Spotify(auth=token["access_token"])
    except Exception as e:
        print(f"[sp_client error uid={chat_id}] {e}")
        return None

def is_connected(chat_id: int) -> bool:
    return os.path.exists(token_cache_path(chat_id))


def get_monitor_status(chat_id: int) -> dict:
    user = load_json(USERS_FILE, {}).get(str(chat_id), {})
    return {
        "status": user.get("monitor_status", "not_checked"),
        "detail": user.get("monitor_detail", "لم يتم الفحص بعد"),
        "last_checked_at": user.get("last_checked_at", "—"),
        "playlist_url": user.get("watch_playlist_url", ""),
    }


def set_playlist_watch(chat_id: int, playlist_url: str) -> str | None:
    match = re.search(r"(?:open\.spotify\.com/playlist/|spotify:playlist:)([A-Za-z0-9]+)", playlist_url)
    if not match:
        return None
    playlist_id = match.group(1)
    users = load_json(USERS_FILE, {})
    user = users.setdefault(str(chat_id), {})
    user["watch_playlist_id"] = playlist_id
    user["watch_playlist_url"] = f"https://open.spotify.com/playlist/{playlist_id}"
    user["monitor_status"] = "not_checked"
    user["monitor_detail"] = "سيتم إنشاء خط أساس للقائمة في أول فحص"
    save_json(USERS_FILE, users)
    return user["watch_playlist_url"]

def disconnect(chat_id: int):
    path = token_cache_path(chat_id)
    if os.path.exists(path):
        os.remove(path)

def process_callback_url(chat_id: int, url: str) -> bool:
    """
    Manually processes a callback URL (e.g. if the redirect to localhost fails).
    """
    try:
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        code  = params.get("code",  [None])[0]
        state = params.get("state", [None])[0]

        if code and state == str(chat_id):
            oauth = get_oauth(chat_id)
            oauth.get_access_token(code, check_cache=False)
            
            users = load_json(USERS_FILE, {})
            users.setdefault(str(chat_id), {}).update({"connected": True, "connected_at": time.strftime("%Y-%m-%d %H:%M")})
            save_json(USERS_FILE, users)
            return True
    except Exception as e:
        print(f"[Manual Auth Error] {e}")
    return False

# ─── Local callback server (handles OAuth redirect for all users) ─────────────
class SpotifyCallbackServer:
    def __init__(self, bot_instance, port=9876):
        self.bot  = bot_instance
        self.port = port
        self._pending = {}   # chat_id -> pkce verifier stored in pkce object itself

    def start(self):
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    parsed = urllib.parse.urlparse(self.path)
                    params = urllib.parse.parse_qs(parsed.query)
                    code  = params.get("code",  [None])[0]
                    state = params.get("state", [None])[0]  # = chat_id

                    if code and state:
                        chat_id = int(state)
                        oauth = get_oauth(chat_id)
                        oauth.get_access_token(code, check_cache=False)  # saves token to cache

                        # Mark user as connected
                        users = load_json(USERS_FILE, {})
                        users.setdefault(str(chat_id), {}).update({"connected": True, "connected_at": time.strftime("%Y-%m-%d %H:%M")})
                        save_json(USERS_FILE, users)

                        # Notify via Telegram
                        try:
                            server.bot.send_message(
                                chat_id,
                                "\u2705 تم ربط حساب Spotify بنجاح!\n"
                                "الآن سأراقب أغانيك المفضلة وأرسل لك إشعاراً عند إضافة أي أغنية جديدة."
                            )
                        except Exception as e:
                            print(f"[Notify error] {e}")

                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write("""
                    <html><body style="font-family:Arial;text-align:center;padding:60px;background:#121212;color:#fff">
                    <h1 style="color:#1DB954">&#x2713; تم الربط بنجاح!</h1>
                    <p>يمكنك إغلاق هذه الصفحة والعودة لتليجرام.</p>
                    </body></html>""".encode("utf-8"))
                except Exception as e:
                    print(f"[Callback Handler Error] {e}")
                    self.send_response(500)
                    self.end_headers()

            def log_message(self, *args):
                pass

        def _run():
            socketserver.TCPServer.allow_reuse_address = True
            with socketserver.TCPServer(("127.0.0.1", self.port), Handler) as httpd:
                httpd.serve_forever()

        threading.Thread(target=_run, daemon=True, name="SpotifyCallbackServer").start()
        print(f"[Spotify] Callback server listening on port {self.port}")


# ─── Spotify Playlist / Liked Songs Poller (per-user) ─────────────────────────
class SpotifyPoller:
    def __init__(self, bot_instance, interval=20):
        self.bot      = bot_instance
        self.interval = interval
        history_state = load_json(HISTORY_FILE, [])
        if isinstance(history_state, dict):
            self.history = set(history_state.get("known_tracks", []))
            self.initialized_users = set(history_state.get("initialized_users", []))
        else:
            self.history = set(history_state)
            self.initialized_users = set()
        self._running = False
        self._reported_failures = {}

    def _save_history(self):
        save_json(HISTORY_FILE, {
            "known_tracks": list(self.history),
            "initialized_users": list(self.initialized_users),
        })

    def _update_user_status(self, chat_id, status, detail=""):
        users = load_json(USERS_FILE, {})
        user = users.setdefault(str(chat_id), {})
        user["monitor_status"] = status
        user["monitor_detail"] = detail
        user["last_checked_at"] = time.strftime("%Y-%m-%d %H:%M")
        save_json(USERS_FILE, users)

    def _report_failure(self, chat_id, error_key, message):
        if self._reported_failures.get(chat_id) == error_key:
            return False
        self._reported_failures[chat_id] = error_key
        try:
            self.bot.send_message(chat_id, message)
        except Exception as error:
            print(f"[Spotify status message error] {error}")
        return True

    def _poll_once(self):
        users = load_json(USERS_FILE, {})
        for chat_id_str, info in users.items():
            if not info.get("connected"):
                continue
            chat_id = int(chat_id_str)
            sp = get_sp_client(chat_id)
            if not sp:
                continue
            try:
                playlist_id = info.get("watch_playlist_id")
                if playlist_id:
                    results = sp.playlist_items(playlist_id, limit=50)
                    source_id = f"playlist:{playlist_id}"
                    source_label = "قائمة Fel7o Inbox"
                else:
                    results = sp.current_user_saved_tracks(limit=50)
                    source_id = "liked"
                    source_label = "المفضلة"
                history_user_key = f"{chat_id_str}:{source_id}"
                seen_keys = set()
                new_tracks = []
                for item in reversed(results.get("items", [])):
                    track = item.get("track")
                    if not track:
                        continue
                    tid = track.get("id")
                    key = f"{chat_id_str}_{source_id}_{tid}"
                    if not tid:
                        continue

                    seen_keys.add(key)

                    title   = track.get("name", "?")
                    artists = ", ".join(a["name"] for a in track.get("artists", []))
                    album   = track.get("album", {}).get("name", "")
                    images  = track.get("album", {}).get("images", [])
                    cover   = images[0]["url"] if images else None
                    sp_url  = track.get("external_urls", {}).get("spotify", "")

                    new_tracks.append((key, tid, title, artists, album, cover, sp_url))

                if history_user_key not in self.initialized_users:
                    self.history.update(seen_keys)
                    self.initialized_users.add(history_user_key)
                    self._save_history()
                    self._update_user_status(chat_id, "ready", f"تم إنشاء خط أساس لـ{source_label}")
                    continue

                for key, tid, title, artists, album, cover, sp_url in new_tracks:
                    if key in self.history:
                        continue
                    self.history.add(key)
                    self._notify(chat_id, tid, title, artists, album, cover, sp_url, source_label)
                self._save_history()
                self._update_user_status(chat_id, "ready", f"متابعة {source_label} تعمل كل 6 ساعات")
                self._reported_failures.pop(chat_id, None)
            except spotipy.SpotifyException as error:
                if error.http_status == 403 and "premium subscription required" in str(error).lower():
                    first_report = self._report_failure(
                        chat_id,
                        "premium_required",
                        "⚠️ متابعة المفضلة متوقفة من Spotify: حساب مالك تطبيق Spotify يحتاج اشتراك Premium نشط. بعد تفعيله قد يستغرق السماح بالخدمة بضع ساعات، ثم ستصل اقتراحات التحميل تلقائيًا."
                    )
                    self._update_user_status(chat_id, "premium_required", "Spotify تطلب Premium لحساب مالك التطبيق لقراءة Playlist")
                else:
                    first_report = self._report_failure(
                        chat_id,
                        f"spotify_{error.http_status}",
                        "⚠️ تعذر الوصول إلى مكتبة Spotify الآن. سأحاول تلقائيًا مرة أخرى لاحقًا."
                    )
                    self._update_user_status(chat_id, f"error_{error.http_status}", "تعذر الوصول إلى مكتبة Spotify")
                if first_report:
                    print(f"[Poller error uid={chat_id_str}] {error}")
            except Exception as e:
                if self._report_failure(
                    chat_id,
                    "connection_error",
                    "⚠️ تعذر الاتصال بـ Spotify مؤقتًا. سأحاول تلقائيًا مرة أخرى لاحقًا."
                ):
                    print(f"[Poller error uid={chat_id_str}] {e}")
                self._update_user_status(chat_id, "connection_error", "تعذر الاتصال بـ Spotify مؤقتًا")

    def _notify(self, chat_id, track_id, title, artists, album, cover, sp_url, source_label):
        from telebot import types

        # Store in tracks map
        tmap = load_json(TRACKS_MAP_FILE, {})
        tmap[track_id] = {"title": title, "artist": artists, "url": sp_url}
        save_json(TRACKS_MAP_FILE, tmap)

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("\u2b07\ufe0f تحميل الآن (320kbps)", callback_data=f"dl_sync:{track_id}"),
            types.InlineKeyboardButton("\u274c تجاهل",                       callback_data=f"ign_sync:{track_id}"),
        )
        caption = (
            f"\U0001f4c1 أغنية جديدة في {source_label}!\n\n"
            f"\U0001f3b5 {title}\n"
            f"\U0001f464 {artists}\n"
            f"\U0001f4bf {album}\n\n"
            f"هل تريد تحميلها؟"
        )
        try:
            if cover:
                self.bot.send_photo(chat_id, cover, caption=caption, reply_markup=markup)
            else:
                self.bot.send_message(chat_id, caption, reply_markup=markup)
        except Exception as e:
            print(f"[Notify error] {e}")

    def start(self):
        if self._running:
            return
        self._running = True
        def _run():
            while self._running:
                try:
                    self._poll_once()
                except Exception as e:
                    print(f"[Poller loop error] {e}")
                time.sleep(self.interval)
        threading.Thread(target=_run, daemon=True, name="SpotifyPoller").start()
        print(f"[Spotify] Playlist poller started (interval={self.interval}s)")

    def stop(self):
        self._running = False

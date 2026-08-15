import re
import json
import urllib.request
import yt_dlp

def clean_url(url: str) -> str:
    cleaned = re.sub(r'/intl-[a-zA-Z-]+/', '/', url)
    if '?' in cleaned:
        cleaned = cleaned.split('?')[0]
    return cleaned.strip()

def search_tracks(query: str, limit: int = 5, mode: str = "track") -> list:
    """Searches YouTube Music-friendly results for the requested media mode."""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        }
    }
    
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_hints = {
                "album": " full album",
                "playlist": " playlist",
                "artist": " artist music",
                "label": " record label music",
            }
            search_query = f"ytsearch{limit}:{query}{search_hints.get(mode, ' audio')}"
            info = ydl.extract_info(search_query, download=False)
            entries = info.get('entries', [])
            
            for idx, entry in enumerate(entries, 1):
                title = entry.get('title', 'Unknown')
                uploader = entry.get('uploader', entry.get('channel', 'Unknown Artist'))
                album = entry.get('album') or entry.get('playlist_title') or entry.get('series') or 'YouTube Music'
                duration = entry.get('duration', 0)
                video_id = entry.get('id', '')
                url = entry.get('url', f"https://www.youtube.com/watch?v={video_id}")
                thumbnail = entry.get('thumbnail', '')
                if not thumbnail and video_id:
                    thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                
                # Format duration into MM:SS
                mins, secs = divmod(int(duration), 60)
                duration_str = f"{mins:02d}:{secs:02d}"
                
                results.append({
                    'index': idx,
                    'id': video_id,
                    'title': title,
                    'artist': uploader,
                    'album': album,
                    'duration': duration,
                    'duration_str': duration_str,
                    'url': url,
                    'thumbnail': thumbnail
                })
    except Exception as e:
        print(f"[Search Error] {e}")

    return results

def get_playlist_tracks(url: str, limit: int = 25) -> list:
    """Extracts list of tracks from a playlist URL (YouTube or Spotify)"""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
        'noplaylist': False,
    }
    tracks = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get('entries', [])
            for entry in entries[:limit]:
                title = entry.get('title', '')
                uploader = entry.get('uploader', entry.get('channel', ''))
                webpage_url = entry.get('url', '')
                if not webpage_url.startswith('http'):
                    vid_id = entry.get('id', '')
                    webpage_url = f"https://www.youtube.com/watch?v={vid_id}"
                tracks.append({
                    'title': title,
                    'artist': uploader,
                    'url': webpage_url
                })
    except Exception as e:
        print(f"[Playlist Extraction Error] {e}")
    return tracks

def get_spotify_info(url: str) -> dict:
    """Extracts Spotify Track/Album/Playlist info"""
    clean = clean_url(url)
    try:
        oembed_url = f"https://open.spotify.com/oembed?url={clean}"
        req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode('utf-8'))
            title = data.get('title', '')
            thumbnail = data.get('thumbnail_url', '')
            obj_type = data.get('type', 'rich')
            
            is_playlist = "playlist" in clean
            is_album = "album" in clean
            
            artist = ""
            if " - " in title:
                parts = title.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip()

            return {
                'title': title,
                'artist': artist,
                'thumbnail': thumbnail,
                'type': 'playlist' if is_playlist else ('album' if is_album else 'track'),
                'url': clean
            }
    except Exception as e:
        print(f"[Spotify Info Error] {e}")
        return None

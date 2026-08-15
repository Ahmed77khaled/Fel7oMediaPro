import os
import glob
import urllib.request
import time
import yt_dlp
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC
import config
from search_engine import get_spotify_info, clean_url

def cleanup_temp_files(max_age_seconds: int = 3600):
    """
    Cleans up old temporary files in TEMP_DIR older than max_age_seconds.
    """
    try:
        if not os.path.exists(config.TEMP_DIR):
            return
        now = time.time()
        for f in os.listdir(config.TEMP_DIR):
            fp = os.path.join(config.TEMP_DIR, f)
            if os.path.isfile(fp):
                if now - os.path.getmtime(fp) > max_age_seconds:
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Cleanup Error] {e}")

def download_video(url: str) -> dict:
    """
    Downloads video from Reels, Shorts, or TikTok using yt-dlp.
    """
    cleanup_temp_files(1800)
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    output_template = os.path.join(config.DOWNLOAD_DIR, "video_%(title)s_%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            # Ensure extension is mp4 if merged
            if not file_path.endswith(".mp4"):
                base = os.path.splitext(file_path)[0]
                if os.path.exists(base + ".mp4"):
                    file_path = base + ".mp4"

            return {
                'status': 'success',
                'file_path': file_path,
                'title': info.get('title', 'Video'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0)
            }
    except Exception as e:
        print(f"[Video Download Error] {e}")
        return {'status': 'error', 'error': str(e)}

def download_podcast(url: str) -> dict:
    """
    Downloads podcast episode from Spotify or YouTube Podcast.
    """
    cleanup_temp_files(1800)
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    output_template = os.path.join(config.DOWNLOAD_DIR, "podcast_%(title)s_%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if not file_path.endswith(".mp3"):
                base = os.path.splitext(file_path)[0]
                if os.path.exists(base + ".mp3"):
                    file_path = base + ".mp3"

            return {
                'status': 'success',
                'file_path': file_path,
                'title': info.get('title', 'Podcast Episode'),
                'duration': info.get('duration', 0)
            }
    except Exception as e:
        print(f"[Podcast Download Error] {e}")
        return {'status': 'error', 'error': str(e)}

def download_audio(target_url_or_id: str, quality: str = config.DEFAULT_BITRATE, spotify_meta: dict = None) -> dict:
    """
    Downloads audio at specified bitrate ('320', '128', 'flac')
    with embedded ID3 tags, high-res cover art, and no volume distortion.
    """
    # Trigger periodic temp cleanup
    cleanup_temp_files(1800)

    if target_url_or_id.startswith("http://") or target_url_or_id.startswith("https://"):
        if "spotify.com" in target_url_or_id:
            spotify_meta = get_spotify_info(target_url_or_id)
            if spotify_meta:
                query = f"{spotify_meta['artist']} - {spotify_meta['title']}" if spotify_meta['artist'] else spotify_meta['title']
                search_target = f"ytsearch1:{query} official audio"
            else:
                search_target = clean_url(target_url_or_id)
        else:
            search_target = target_url_or_id
    else:
        # YouTube ID or query
        if len(target_url_or_id) == 11 and not " " in target_url_or_id:
            search_target = f"https://www.youtube.com/watch?v={target_url_or_id}"
        else:
            search_target = f"ytsearch1:{target_url_or_id} audio"

    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    output_template = os.path.join(config.DOWNLOAD_DIR, "%(title)s_%(id)s.%(ext)s")

    is_flac = quality.lower() == "flac"
    codec = "flac" if is_flac else "mp3"
    bitrate = "320" if quality == "320" else ("128" if quality == "128" else "320")

    audio_postprocessor = {
        'key': 'FFmpegExtractAudio',
        'preferredcodec': codec,
    }
    if not is_flac:
        audio_postprocessor['preferredquality'] = bitrate

    postprocessors = [
        audio_postprocessor,
        {
            'key': 'FFmpegMetadata',
            'add_metadata': True,
        },
        {
            'key': 'EmbedThumbnail',
        }
    ]

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web']
            }
        },
        'postprocessors': postprocessors,
        'writethumbnail': True,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_target, download=True)
            if 'entries' in info and info['entries']:
                info = info['entries'][0]

            title = info.get('title', 'Unknown Title')
            artist = info.get('uploader', info.get('artist', 'Unknown Artist'))
            duration = info.get('duration', 0)
            thumbnail_url = info.get('thumbnail', '')
            video_id = info.get('id', '')

            # Use Spotify metadata if available
            if spotify_meta:
                if spotify_meta.get('title'):
                    title = spotify_meta['title']
                if spotify_meta.get('artist'):
                    artist = spotify_meta['artist']

            # Locate downloaded file
            ext = codec
            matches = []
            for f in os.listdir(config.DOWNLOAD_DIR):
                if video_id in f and f.endswith(f".{ext}"):
                    matches.append(os.path.join(config.DOWNLOAD_DIR, f))
            
            if not matches:
                # Fallback: find any file with video_id in name
                for f in os.listdir(config.DOWNLOAD_DIR):
                    if video_id in f:
                        matches.append(os.path.join(config.DOWNLOAD_DIR, f))

            if not matches:
                return {'status': 'error', 'error': 'Downloaded file not found on disk.'}

            file_path = max(matches, key=os.path.getmtime)

            # Inject ID3 tags manually if MP3
            if ext == 'mp3':
                try:
                    audio = ID3(file_path)
                except Exception:
                    audio = ID3()
                audio.add(TIT2(encoding=3, text=title))
                audio.add(TPE1(encoding=3, text=artist))
                audio.save(file_path)

            thumb_path = None
            if thumbnail_url:
                try:
                    thumb_path = os.path.join(config.TEMP_DIR, f"thumb_{video_id}.jpg")
                    urllib.request.urlretrieve(thumbnail_url, thumb_path)
                except Exception:
                    thumb_path = None

            return {
                'status': 'success',
                'file_path': file_path,
                'title': title,
                'artist': artist,
                'duration': int(duration),
                'thumbnail_path': thumb_path,
                'quality': quality
            }
    except Exception as e:
        print(f"[Download Error] {e}")
        return {
            'status': 'error',
            'error': str(e)
        }

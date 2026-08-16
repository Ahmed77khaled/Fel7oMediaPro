import importlib
import os
import pathlib
import sys
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def test_main_import_and_html_helper():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["BOT_TOKEN"] = "123456789:TEST_TOKEN_FOR_LOCAL_IMPORT_ONLY"
        os.environ["BOT_USERNAME"] = "Fel7oMediaBot"
        os.environ["DATA_DIR"] = os.path.join(temp_dir, "data")
        os.environ["TEMP_DIR"] = os.path.join(temp_dir, "temp")
        os.environ["DOWNLOAD_DIR"] = os.path.join(temp_dir, "downloads")
        os.environ["WEBHOOK_URL"] = ""

        import config
        importlib.reload(config)
        sys.modules.pop("main", None)
        main = importlib.import_module("main")

        escaped = main.html_text("حمو المرشدي & <live> _test_")
        assert "&amp;" in escaped
        assert "&lt;live&gt;" in escaped
        assert "_test_" in escaped


if __name__ == "__main__":
    test_main_import_and_html_helper()
    print("main import smoke test passed")


def test_send_audio_caption_is_safe():
    from unittest.mock import Mock

    import main

    audio_path = PROJECT_ROOT / "tests" / "fixture_audio.mp3"
    audio_path.write_bytes(b"not-real-audio")
    try:
        main.time.sleep = lambda *_args: None
        main.downloader.download_audio = Mock(
            return_value={
                "status": "success",
                "file_path": str(audio_path),
                "title": "A & B <live>_test_",
                "artist": "Artist > Guest",
                "duration": 42,
                "thumbnail_path": None,
                "quality": "320",
            }
        )
        main.record_recent_download = Mock()
        main.bot.send_audio = Mock()
        main.bot.send_message = Mock()

        assert main.send_audio(123, "test query", "320") is True
        kwargs = main.bot.send_audio.call_args.kwargs
        assert kwargs["parse_mode"] == "HTML"
        assert "&amp;" in kwargs["caption"]
        assert "&lt;live&gt;" in kwargs["caption"]
        assert "Artist &gt; Guest" in kwargs["caption"]
    finally:
        audio_path.unlink(missing_ok=True)


if __name__ == "__main__":
    test_main_import_and_html_helper()
    test_send_audio_caption_is_safe()
    print("main import and media caption smoke tests passed")

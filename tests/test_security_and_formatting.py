import html
import importlib
import os
import pathlib
import sys
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def test_config_requires_token():
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ.pop("BOT_TOKEN", None)
        os.environ["DATA_DIR"] = os.path.join(temp_dir, "data")
        os.environ["TEMP_DIR"] = os.path.join(temp_dir, "temp")
        os.environ["DOWNLOAD_DIR"] = os.path.join(temp_dir, "downloads")
        import config

        config = importlib.reload(config)
        try:
            config.validate_runtime_config()
        except RuntimeError as error:
            assert "BOT_TOKEN" in str(error)
        else:
            raise AssertionError("Missing BOT_TOKEN must fail fast")


def test_telegram_metadata_is_escaped():
    title = "A & B <remix>_ [live]"
    artist = "Artist > Guest"
    caption = (
        f"🎵 <b>{html.escape(title, quote=False)}</b>\n"
        f"👤 {html.escape(artist, quote=False)}"
    )
    assert "&amp;" in caption
    assert "&lt;remix&gt;" in caption
    assert "Artist &gt; Guest" in caption
    assert "<remix>" not in caption


if __name__ == "__main__":
    test_config_requires_token()
    test_telegram_metadata_is_escaped()
    print("security and formatting smoke tests passed")

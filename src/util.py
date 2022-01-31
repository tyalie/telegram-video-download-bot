from yt_dlp.utils import YoutubeDLError
import base64
import secrets


def generate_token(length: int = 8) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ASCII")


def validate_query(url: str) -> bool:
    return True


def clean_yt_error(error: YoutubeDLError, max_length: int = 90) -> str:
    text = error.msg
    if text.startswith("ERROR: "):
        text = text[7:]

    if len(text) > max_length:
        text = text[:max_length] + "…"
    return text

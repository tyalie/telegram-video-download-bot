from yt_dlp.utils import YoutubeDLError


def validate_query(url: str) -> bool:
    return True


def clean_yt_error(error: YoutubeDLError, max_length: int = 90) -> str:
    text = error.msg
    if text.startswith("ERROR: "):
        text = text[7:]

    if len(text) > max_length:
        text = text[:max_length] + "…"
    return text

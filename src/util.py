from yt_dlp.utils import YoutubeDLError


def validate_query(url: str) -> bool:
    return True


def clean_yt_error(error: YoutubeDLError) -> str:

    return error.msg

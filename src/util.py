from yt_dlp.utils import YoutubeDLError
import logging
import base64
import secrets


def generate_token(length: int = 8) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(length)).decode("ASCII")


def validate_query(url: str) -> bool:
    return True


def clean_yt_error(error: YoutubeDLError, max_length: int = 90) -> str:
    text = error.msg
    if text.startswith("ERROR: "):
        text = text[7:]

    if len(text) > max_length:
        text = text[:max_length] + "…"
    return text


def check_ffmpeg(quiet: bool = False) -> bool:
    from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor, FFmpegPostProcessorError

    try:
        FFmpegPostProcessor().check_version()
        return True
    except FFmpegPostProcessorError:
        if not quiet:
            logging.error(
                "ffmpeg / ffprobe not found. Please install executable."
                "Otherwise features like merge will be missing"
            )
    return False



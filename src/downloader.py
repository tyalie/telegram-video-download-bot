from typing import Dict, Any
from yt_dlp import YoutubeDL
from pathlib import Path
import base64
import secrets
import tempfile
import logging
from dataclasses import dataclass

from plugins.tumblr import TumblrIE
from settings import config


@dataclass
class VideoInfo:
    filepath: Path
    title: str
    ext: str
    duration_s: int

    @property
    def orig_filename(self) -> str:
        return f"{self.title}.{self.ext}"


class Downloader:
    def __init__(self):
        self._temporary_dir = tempfile.TemporaryDirectory()
        logging.debug(f"Using temporary dictionary {self._temporary_dir.name}")

    def _get_opts(self, filename) -> Dict[str, Any]:
        return {
            "format": "(mp4,webm)",
            "outtmpl": f"{filename}.%(ext)s",
            "paths": {
                "home": self._temporary_dir.name
            },
            "match_filter": self._filter_length,
            "noplaylist": True
        }

    def _get_temp_file_name(self) -> str:
        uuid = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ASCII")
        path = Path(self._temporary_dir.name) / uuid 
        return str(path)

    def _filter_length(self, info_dict, *args, **kwargs):
        duration = info_dict.get("duration", 0)
        if duration < config.max_video_length_s:
            return None
        return f"Rejected: Video is to long with {duration}s" 

    def _finished_hook(self, info):
        if info["status"] == "finished":
            print(info["filename"])

    def _get_info_with_download(self, ydl: YoutubeDL, url: str) -> Dict[str, Any]:
        extra_info = {}
        if "tumblr" in url:
            extra_info["http_headers"] = {
                "Referer": url
            }

        return ydl.extract_info(url, download=True, extra_info=extra_info)

    def download(self, url: str):
        filename = self._get_temp_file_name()
        logging.debug(f"Download: Writing to '{filename}'")
        with YoutubeDL(self._get_opts(filename)) as ydl:
            ydl.add_info_extractor(TumblrIE())
            ydl.add_progress_hook(self._finished_hook)
            info = self._get_info_with_download(ydl, url)

            filepath = Path(f"{filename}.{info['ext']}")
            if not filepath.is_file():
                raise RuntimeError("Downloaded file could not be found")

            return VideoInfo(
                filepath=filepath,
                title=info["title"],
                ext=info["ext"],
                duration_s=info.get("duration", None)
            )

    def __del__(self):
        logging.debug("Download: Cleaning up temporary dictionary")
        self._temporary_dir.cleanup()

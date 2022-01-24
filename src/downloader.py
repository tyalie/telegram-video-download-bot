from typing import Dict, Any
from yt_dlp import YoutubeDL
from pathlib import Path
import base64
import secrets
import tempfile
import logging
from dataclasses import dataclass

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
            "match_filter": self._filter_length
        }

    def _get_temp_file_name(self) -> str:
        uuid = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ASCII")
        path = Path(self._temporary_dir.name) / uuid 
        return str(path)

    def _filter_length(self, info_dict, *args, **kwargs):
        duration = info_dict["duration"]
        if duration < config.max_video_length_s:
            return None
        return f"Rejected: Video is to long with {duration}s" 

    def _finished_hook(self, info):
        if info["status"] == "finished":
            print(info["filename"])

    def download(self, url: str):
        filename = self._get_temp_file_name()
        logging.debug(f"Download: Writing to '{filename}'")
        with YoutubeDL(self._get_opts(filename)) as ydl:
            ydl.add_progress_hook(self._finished_hook)
            info = ydl.extract_info(url, download=True)

            filepath = Path(f"{filename}.{info['ext']}")
            if not filepath.is_file():
                raise RuntimeError("Downloaded file could not be found")

            return VideoInfo(
                filepath=filepath,
                title=info["title"],
                ext=info["ext"],
                duration_s=info["duration"]
            )

    def __del__(self):
        logging.debug("Download: Cleaning up temporary dictionary")
        self._temporary_dir.cleanup()

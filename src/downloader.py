from typing import Dict, Any
from yt_dlp import YoutubeDL
from yt_dlp.utils import random_user_agent, YoutubeDLError
from pathlib import Path
import base64
import secrets
import tempfile
import logging
from dataclasses import dataclass

from plugins.tumblr import TumblrIE
from plugins.youtube_dl_injection import YoutubeDL2
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
        self.counter = 0

    def _get_opts(self, filename, url) -> Dict[str, Any]:
        return {
            "format": "(mp4,webm)",
            "outtmpl": f"{filename}.%(ext)s",
            "paths": {
                "home": self._temporary_dir.name
            },
            "match_filter": self._filter_length,
            "noplaylist": True,
            "http_headers": self._get_custom_headers_from_url(url),
            "socket_timeout": config.yt_socket_timeout,
            "debug_printtraffic": config.debug_yt_traffic,
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
        return ydl.extract_info(url, download=True, extra_info=extra_info)

    def _get_custom_headers_from_url(self, url: str) -> Dict:
        headers = {"User-Agent": random_user_agent()}

        if "tiktok" in url:
            # see https://github.com/yt-dlp/yt-dlp/issues/2396
            headers.update({"User-Agent": "facebookexternalhit/1.1"})

        return headers

    def hook(self, data):
        data = YoutubeDL.sanitize_info(data)
        import json
        with open(f"/tmp/logs/yt.{self.counter}.json", "w") as f:
            json.dump(data, f)
            self.counter += 1

    def download(self, url: str):
        filename = self._get_temp_file_name()
        logging.debug(f"Download: Writing to '{filename}'")

        with YoutubeDL2(self._get_opts(filename, url)) as ydl:
            ydl.add_progress_hook(self.hook)
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

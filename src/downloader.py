from typing import Dict, Any, Optional, Callable
from yt_dlp import YoutubeDL
from yt_dlp.utils import random_user_agent, DownloadError, UnsupportedError
from yt_dlp.postprocessor import FFmpegVideoRemuxerPP
from time import time
from pathlib import Path
import tempfile
import logging
from dataclasses import dataclass, field

from plugins.tumblr import TumblrIE
from plugins.youtube_dl_injection import YoutubeDL2
from settings import config
from util import generate_token


@dataclass
class VideoInfo:
    filepath: Path
    title: str
    ext: str
    duration_s: int
    uuid: str = field(init=False, default_factory=generate_token)
    _creation: float = field(init=False, default_factory=time)

    @property
    def orig_filename(self) -> str:
        return f"{self.title}.{self.ext}"


class MyLogger:
    def debug(self, msg):
        if msg.startswith('[debug] '):
            ...
        else:
            self.info(msg)

    def info(self, msg):
        ...

    def warning(self, msg):
        ...

    def error(self, msg):
        logging.error(self._remove_prefix(msg))

    def _remove_prefix(self, msg: str) -> str:
        return msg[msg.find(']') + 1:]


class Downloader:
    def __init__(self):
        self._temporary_dir = tempfile.TemporaryDirectory()
        self._downloaded_video_cache: Dict[str, VideoInfo] = {}

        logging.debug(f"Using temporary dictionary {self._temporary_dir.name}")

    def _get_opts(self, filename, url) -> Dict[str, Any]:
        return {
            # prefer h264, … over vp9 and have video be 480p or smallest 
            "format_sort": ["+vcodec:avc", "+acodec:m4a", "res:480"],
            "outtmpl": f"{filename}.%(ext)s",
            "paths": {
                "home": self._temporary_dir.name
            },
            "match_filter": self._video_filter,
            "noplaylist": True,
            "logger": MyLogger(),
            "http_headers": self._get_custom_headers_from_url(url),
            "break_on_reject": True,

            "socket_timeout": config.yt_socket_timeout,
            "debug_printtraffic": config.debug_yt_traffic,
            "quiet": config.yt_quiet_mode,
            "no_color": True,
        }

    def _get_temp_file_name(self) -> str:
        uuid = generate_token(32)
        path = Path(self._temporary_dir.name) / uuid 
        return str(path)

    def _video_filter(self, info_dict, *args, **kwargs):
        results = list(
            filter(lambda v: v is not None, 
                   map(lambda f: f(info_dict), [
                       self._filter_is_live,
                       self._filter_length
                   ])
        ))

        if len(results) > 0:
            raise DownloadError(results[0], UnsupportedError(info_dict.get("original_url", "")))
        return None

    def _filter_length(self, info_dict, *args, **kwargs):
        """Filters videos by their length in s to remove very large ones"""
        duration = info_dict.get("duration", 0)
        if duration is None or duration < config.max_video_length_s:
            return None
        return f"Rejected: Video is to long with {duration}s"

    def _filter_is_live(self, info_dict, *args, **kwargs):
        """Filters video whether it's a live stream or not"""
        if not info_dict.get("is_live", False):
            return None
        return "Rejected: Video is a live feed"

    def _finished_hook(self, info):
        if info["status"] == "finished":
            logging.debug(f"Downloaded file: {info['filename']}")

    def _get_info_with_download(self, ydl: YoutubeDL, url: str) -> Dict[str, Any]:
        extra_info = {}
        return ydl.extract_info(url, download=True, extra_info=extra_info)

    def _get_custom_headers_from_url(self, url: str) -> Dict:
        headers = {"User-Agent": random_user_agent()}

        if "tiktok" in url:
            # see https://github.com/yt-dlp/yt-dlp/issues/2396
            headers.update({"User-Agent": "facebookexternalhit/1.1"})

        return headers

    def download(self, url: str, progress_handler: Optional[Callable[[Dict], None]] = None):
        filename = self._get_temp_file_name()
        logging.debug(f"Download: Writing to '{filename}'")

        with YoutubeDL2(self._get_opts(filename, url)) as ydl:
            if progress_handler is not None:
                ydl.add_progress_hook(progress_handler)

            # add additional extractor plugins
            ydl.add_info_extractor(TumblrIE())

            ydl.add_post_processor(FFmpegVideoRemuxerPP(ydl, "mp4"))
            ydl.add_progress_hook(self._finished_hook)
            info = self._get_info_with_download(ydl, url)
            info['ext'] = "mp4"

            filepath = Path(f"{filename}.{info['ext']}")
            if not filepath.is_file():
                raise RuntimeError(f"Downloaded file could not be found ({filepath})")

            vinfo = VideoInfo(
                filepath=filepath,
                title=info["title"],
                ext=info["ext"],
                duration_s=info.get("duration", None)
            )

            self._downloaded_video_cache[vinfo.uuid] = vinfo
            return vinfo

    def release_video(self, uuid: str):
        if (vinfo := self._downloaded_video_cache.get(uuid)) is None:
            return

        logging.debug(f"Download: Releasing {vinfo.filepath} | {vinfo.uuid}")
        if vinfo.filepath.is_file():
            vinfo.filepath.unlink()
        else:
            logging.warning(f"Download: File {vinfo.filepath} | {vinfo.uuid} doesn't exist")

        del self._downloaded_video_cache[uuid]

    def __del__(self):
        logging.debug("Download: Cleaning up temporary dictionary")
        self._temporary_dir.cleanup()

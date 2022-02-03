from typing import Dict, Any, Optional, Callable, Tuple
from yt_dlp import YoutubeDL
from yt_dlp.utils import random_user_agent, DownloadError, UnsupportedError, YoutubeDLError
from yt_dlp.postprocessor import FFmpegVideoRemuxerPP
from time import time
from pathlib import Path
import tempfile
import logging
from dataclasses import dataclass, field

from plugins.tumblr import TumblrIE
from plugins.youtube_dl_injection import YoutubeDL2
from settings import config
from resourcemanager import resource_manager 
from util import generate_token


@dataclass
class VideoInfo:
    filepath: Path
    title: str
    ext: str
    duration_s: int
    uuid: str
    _creation: float = field(init=False, default_factory=time)

    def __post_init__(self):
        if self.title is None or len(self.title) == 0:
            self.title = resource_manager.get_string("video_no_title")

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
        keywords = ["ffmpeg"]

        should_log = config.debug
        should_log |= any(map(lambda k: k in msg.lower(), keywords))

        if should_log:
            logging.warning(self._remove_prefix(msg))

    def error(self, msg):
        logging.error(self._remove_prefix(msg))

    def _remove_prefix(self, msg: str) -> str:
        return msg[msg.find(']') + 1:]


class Downloader:
    def __init__(self, temp_dir: Optional[tempfile.TemporaryDirectory] = None):
        self._temp_dir: tempfile.TemporaryDirectory = None
        if temp_dir is not None:
            self._init_temp_dir(temp_dir)

    def _init_temp_dir(self, temp_dir):
        self._temp_dir = temp_dir
        logging.debug(f"Using temporary dictionary {self._temp_dir.name}")

    def __enter__(self):
        if self._temp_dir is None:
            self._init_temp_dir(tempfile.TemporaryDirectory())
        return self

    def __exit__(self, exc, value, tb):
        self._temp_dir.cleanup()

    def _get_opts(self, filename, url: str) -> Dict[str, Any]:
        return {
            "format_sort": ["res:480"],
            "outtmpl": f"{filename}.%(ext)s",
            "paths": {
                "home": self._temp_dir.name
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

    def _get_temp_file_name(self) -> Tuple[str, str]:
        uuid = generate_token(16)
        return str(Path(self._temp_dir.name) / uuid), uuid

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
        return resource_manager.get_string("reject_too_long", duration=duration)

    def _filter_is_live(self, info_dict, *args, **kwargs):
        """Filters video whether it's a live stream or not"""
        if not info_dict.get("is_live", False):
            return None
        return resource_manager.get_string("reject_is_live")

    def _finished_hook(self, info):
        if info["status"] == "finished":
            logging.debug(f"Downloaded file: {info['filename']}")

    def _get_info_with_download(self, ydl: YoutubeDL, url: str) -> Dict[str, Any]:
        extra_info = {}
        return ydl.extract_info(url, download=True, extra_info=extra_info)

    def _get_custom_headers_from_url(self, url: str) -> Dict:
        headers = {"User-Agent": random_user_agent()}
        url = url.lower()

        if "tiktok" in url:
            # see https://github.com/yt-dlp/yt-dlp/issues/2396
            headers.update({"User-Agent": "facebookexternalhit/1.1"})

        return headers

    def _start_download(self, url: str, filename: Path, token: str, ydl: YoutubeDL) -> VideoInfo:
        # add additional extractor plugins
        ydl.add_info_extractor(TumblrIE())

        ydl.add_post_processor(FFmpegVideoRemuxerPP(ydl, "mp4"))
        ydl.add_progress_hook(self._finished_hook)
        info = self._get_info_with_download(ydl, url)
        info['ext'] = "mp4"

        filepath = self._get_main_filepath(info)
        if filepath is None or not filepath.is_file():
            raise YoutubeDLError(f"Downloaded file could not be found ({filepath})")

        vinfo = VideoInfo(
            filepath=filepath,
            title=info["title"],
            ext=info["ext"],
            duration_s=info.get("duration", None),
            uuid=token
        )

        return vinfo

    def start(self, url: str, progress_handler: Optional[Callable[[Dict], None]] = None) -> VideoInfo:
        filename, token = self._get_temp_file_name()
        logging.debug(f"Download: Writing to '{filename}'")

        with YoutubeDL2(self._get_opts(filename, url)) as ydl:
            if progress_handler is not None:
                ydl.add_progress_hook(progress_handler)

            return self._start_download(url, filename, token, ydl)

    @staticmethod
    def _get_main_filepath(info: Dict[str, Any]) -> Optional[Path]:
        if (l := len(info["requested_downloads"])) == 0:
            return
        elif l > 1:
            return RuntimeError("More than one requested download")

        download = info["requested_downloads"][0]

        return Path(download["filepath"]) if "filepath" in download else None

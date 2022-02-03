from typing import Dict, Any, Optional, Callable, Union, List, Tuple
from multiprocessing import RLock
from yt_dlp import YoutubeDL
from functools import reduce
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
    def __init__(self):
        self._temporary_dir = tempfile.TemporaryDirectory()
        self._downloaded_video_cache: Dict[str, Dict[str, Union[str, List]]] = {}
        self._video_cache_lock = RLock()

        logging.debug(f"Using temporary dictionary {self._temporary_dir.name}")

    def _get_opts(self, filename, url) -> Dict[str, Any]:
        return {
            "format_sort": ["res:480"],
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

    def _get_temp_file_name(self) -> Tuple[str, str]:
        uuid = generate_token(16)
        path = Path(self._temporary_dir.name) / uuid 
        return str(path), uuid

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

        filepath = Path(f"{filename}.{info['ext']}")

        file_names = self._get_all_filepaths(info)

        with self._video_cache_lock:
            self._downloaded_video_cache[token] = file_names

        if file_names["main"] is None or not (filepath := Path(file_names["main"])).is_file():
            raise YoutubeDLError(f"Downloaded file could not be found ({filepath})")

        vinfo = VideoInfo(
            filepath=filepath,
            title=info["title"],
            ext=info["ext"],
            duration_s=info.get("duration", None),
            uuid=token
        )

        return vinfo

    def download(self, url: str, progress_handler: Optional[Callable[[Dict], None]] = None):
        filename, token = self._get_temp_file_name()
        logging.debug(f"Download: Writing to '{filename}'")

        with YoutubeDL2(self._get_opts(filename, url)) as ydl:
            if progress_handler is not None:
                ydl.add_progress_hook(progress_handler)

            try:
                return self._start_download(url, filename, token, ydl)
            finally:
                self._cleanup(token, True)

    def release_video(self, uuid: str):
        self._cleanup(uuid, False)

        # check for inconsitencies
        leftovers = list(Path(self._temporary_dir.name).glob(f"./{uuid}*"))
        if len(leftovers) != 0:
            logging.error(f"Even after full cleanup of {uuid} some files remained ({leftovers})")

    def _cleanup(self, token: str, only_tmp: bool):
        with self._video_cache_lock:
            if (files := self._downloaded_video_cache.get(token)) is None:
                logging.warning(f"Nothing to clean for {token}")
                return

            file_set = set(reduce(lambda o, n: o + (n if type(n) is list else [n]), files.values(), []))
            if only_tmp:
                file_set -= {files["main"]}

            for file in file_set:
                if file is not None and (file := Path(file)).is_file():
                    logging.debug(f"Cleaning {token}: {file}")
                    file.unlink()

            for key in list(files.keys()):
                if only_tmp and key == "main":
                    continue
                del files[key]

            if len(files) == 0:
                del self._downloaded_video_cache[token]

    @staticmethod
    def _get_all_filepaths(info: Dict[str, Any]) -> Dict[str, Union[str, List]]:
        if (l := len(info["requested_downloads"])) == 0:
            return
        elif l > 1:
            return RuntimeError("More than one requested download")

        download = info["requested_downloads"][0]

        file_dir = {
            "main": download.get("filepath"),
            "premux": download.get("_filename"),
            "formats": list(map(lambda f: f.get("filepath"), download.get("requested_formats", [])))
        }

        return file_dir

    def __del__(self):
        logging.debug("Download: Cleaning up temporary dictionary")
        self._temporary_dir.cleanup()

from threading import Event, Thread
from multiprocessing import Process
from telegram import (
    Bot, InlineQuery, InlineQueryResultCachedVideo, TelegramError, 
    InlineQueryResultArticle, InputTextMessageContent, Message
)
import logging
from typing import Optional
from yt_dlp.utils import YoutubeDLError, DownloadCancelled
from dataclasses import dataclass

from resourcemanager import ResourceManager
from downloader import Downloader

from util import validate_query, clean_yt_error
from downloader import VideoInfo


class InlineQueryRespondDispatcher:
    def __init__(
        self, bot: Bot, resource_manager: ResourceManager,
        downloader: Downloader, devnullchat: int
    ):
        self._devnullchat = devnullchat
        self._downloader = downloader
        self._resource_man = resource_manager
        self._bot = bot

        self._next_query_arrived_events = {}

    def dispatchInlineQueryResponse(self, inline_query: InlineQuery):
        logging.debug(f"Received inline query {inline_query}")

        try:
            self._next_query_arrived_events[inline_query.from_user.id].is_set()
        except KeyError:
            ...
        finally:
            self._next_query_arrived_events[inline_query.from_user.id] = Event()

        responder = Process(
            target=self._respondToInlineQuery,
            args=[inline_query, self._next_query_arrived_events[inline_query.from_user.id]]
        )
        responder.start()
        Thread(target=self.joinProcess, args=[responder, inline_query.query]).start()

    def joinProcess(self, process, query):
        logging.debug(f"Starting process - '{query}' {process}")
        process.join()
        logging.debug(f"Ending process - {process}")

    def _build_progress_handler(self, next_arrived_event: Event):
        def handler(data):
            if next_arrived_event.is_set():
                raise DownloadCancelled()
        return handler

    def _respondToInlineQuery(self, inline_query: InlineQuery, next_arrived_event: Event):
        query = inline_query.query
        query_id = inline_query.id

        if not validate_query(query):
            return

        info = None
        video_cache = None
        result = None

        try:
            if not next_arrived_event.is_set():
                info = self._downloader.download(query, self._build_progress_handler(next_arrived_event))

            if not next_arrived_event.is_set():
                video_cache = self._upload_video(info)

            if not next_arrived_event.is_set() and video_cache is not None:
                media_id = video_cache.video.file_id
                result = InlineQueryResultCachedVideo(
                    0, video_file_id=media_id, title=info.title, caption=query
                )
                logging.info("Served inline video request")
        except TelegramError as err:
            logging.warn("Error handling inline query", exc_info=err)
            result = InlineQueryResultArticle(
                0, self._resource_man.get_string("error_inline_telegram_title"),
                InputTextMessageContent(err.message), description=str(err)
            )
        except YoutubeDLError as err:
            result = InlineQueryResultArticle(
                0, self._resource_man.get_string("error_inline_download_title"),
                InputTextMessageContent(f"Error downloading: {inline_query.query}"),
                description=clean_yt_error(err)
            )
        finally:
            if info is not None:
                self._downloader.release_video(info.uuid)
            if video_cache is not None:
                video_cache.delete()

            if not next_arrived_event.is_set() and result is not None:
                self._bot.answerInlineQuery(query_id, [result], cache_time=0)
                logging.debug(f"Answered to inline query '{query}'")

    def _upload_video(self, info: VideoInfo) -> Message:
        try:
            v_msg = self._bot.send_video(
                self._devnullchat, open(info.filepath, "rb"), 
                filename=info.orig_filename
            )
            logging.debug(f"Video {info.orig_filename} uploaded successfully")
            return v_msg
        except TelegramError as err:
            logging.warn(f"Telegram Error occured: {err}")


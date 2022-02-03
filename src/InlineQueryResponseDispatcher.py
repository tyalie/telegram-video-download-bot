from threading import Thread, Lock
from multiprocessing import Process
from telegram import (
    Bot, InlineQuery, InlineQueryResultCachedVideo, TelegramError,
    InlineQueryResultArticle, InputTextMessageContent, Message
)
import logging
import signal
from typing import Optional
from yt_dlp.utils import YoutubeDLError
from dataclasses import dataclass

from resourcemanager import resource_manager

from util import validate_query, clean_yt_error
from downloader import VideoInfo, Downloader


@dataclass
class Query:
    process: Optional[Process] = None


class InlineQueryRespondDispatcher:
    def __init__(
        self, bot: Bot, devnullchat: int
    ):
        self.devnullchat = devnullchat
        self.bot = bot

        self._next_query_lock = Lock()
        self._next_query_arrived_events = {}

    def dispatchInlineQueryResponse(self, inline_query: InlineQuery):
        logging.debug(f"Received inline query {inline_query}")

        with self._next_query_lock:
            try:
                query = self._next_query_arrived_events[inline_query.from_user.id]
                # needing to terminate process as there is no trivial
                # way to stop YoutubeDL during the download
                if query.process is not None:
                    query.process.terminate()
            except KeyError:
                ...
            finally:
                new_query = Query()
                self._next_query_arrived_events[inline_query.from_user.id] = new_query

        responder = InlineQueryResponse(inline_query, self.bot, self.devnullchat)
        process = Process(target=responder.start_process)
        self._next_query_arrived_events[inline_query.from_user.id].process = process
        process.start()
        Thread(target=self.joinProcess, args=[process, inline_query.query]).start()

    def joinProcess(self, process, query):
        logging.debug(f"Starting process - '{query}' {process}")
        process.join()
        logging.debug(f"Ending process - {process}")


class StopProcessException(Exception):
    ...


class InlineQueryResponse:
    def __init__(
        self, inline_query: InlineQuery, bot: Bot, devnullchat: int
    ):
        self.inline_query = inline_query
        self._bot = bot
        self._devnullchat = devnullchat

        self.video_cache = None

    def _handle_sigterm(self, signum, frame):
        logging.debug(f"Forcing inline response to close due to {signum} | {self}")
        raise StopProcessException()

    def start_process(self, *args, **kwargs):
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        try:
            self.respondToInlineQuery(*args, **kwargs)
        except TypeError as err:
            if str(err) != "handler() has 0 arguments but 2 where given":
                raise err
        except StopProcessException:
            ...
        finally:
            self._close_down()

    def respondToInlineQuery(self):
        query = self.inline_query.query
        query_id = self.inline_query.id

        if not validate_query(query):
            return

        try:
            with Downloader() as downloader:
                info = downloader.download(query)
                self.video_cache = self._upload_video(info)

            if self.video_cache is not None:
                media_id = self.video_cache.video.file_id
                result = InlineQueryResultCachedVideo(
                    0, video_file_id=media_id, title=info.title, caption=query
                )
        except TelegramError as err:
            logging.warn("Error handling inline query", exc_info=err)
            result = InlineQueryResultArticle(
                0, resource_manager.get_string("error_inline_telegram_title"),
                InputTextMessageContent(err.message), description=str(err)
            )
        except YoutubeDLError as err:
            result = InlineQueryResultArticle(
                0, resource_manager.get_string("error_inline_download_title"),
                InputTextMessageContent(f"Error downloading: {query}"),
                description=clean_yt_error(err)
            )
        finally:
            self._bot.answerInlineQuery(query_id, [result], cache_time=0)
            logging.debug(f"Answered to inline query '{query}'")

    def _close_down(self):
        logging.debug("Cleaning up query {self}")
        if self.video_cache is not None:
            self.video_cache.delete()
            self.video_cache = None

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

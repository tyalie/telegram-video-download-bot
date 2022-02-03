from threading import Thread, Lock
from multiprocessing import Process, Event
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
from downloader import Downloader

from util import validate_query, clean_yt_error
from downloader import VideoInfo


@dataclass
class Query:
    event: Event
    process: Optional[Process]


class InlineQueryRespondDispatcher:
    def __init__(
        self, bot: Bot, downloader: Downloader, devnullchat: int
    ):
        self.devnullchat = devnullchat
        self.bot = bot
        self.downloader = downloader

        self._next_query_lock = Lock()
        self._next_query_arrived_events = {}

    def dispatchInlineQueryResponse(self, inline_query: InlineQuery):
        logging.debug(f"Received inline query {inline_query}")

        with self._next_query_lock:
            try:
                query = self._next_query_arrived_events[inline_query.from_user.id]
                query.event.set()
                # needing to terminate process as there is no trivial 
                # way to stop YoutubeDL during the download
                if query.process is not None:
                    query.process.terminate()
            except KeyError:
                ...
            finally:
                new_query = Query(Event(), None)
                self._next_query_arrived_events[inline_query.from_user.id] = new_query

        responder = InlineQueryResponse(inline_query, new_query.event, self)
        process = Process(
            target=responder.start_process,
        )
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
        self, inline_query: InlineQuery, new_arrived_event: Event, 
        dispatcher: InlineQueryRespondDispatcher
    ):
        self.inline_query = inline_query
        self.next_arrived_event = new_arrived_event
        self.dispatcher = dispatcher

        self.info = None
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
            if not self.next_arrived_event.is_set():
                self.info = self.dispatcher.downloader.download(query)
            if not self.next_arrived_event.is_set():
                self.video_cache = self._upload_video(self.info)

            if self.video_cache is not None:
                media_id = self.video_cache.video.file_id
                result = InlineQueryResultCachedVideo(
                    0, video_file_id=media_id, title=self.info.title, caption=query
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
            if not self.next_arrived_event.is_set():
                self.dispatcher.bot.answerInlineQuery(query_id, [result], cache_time=0)
                logging.debug(f"Answered to inline query '{query}'")

    def _close_down(self):
        logging.debug("Cleaning up query {self}")
        if self.info is not None:
            self.dispatcher.downloader.release_video(self.info.uuid)
            self.info = None
        if self.video_cache is not None:
            self.video_cache.delete()
            self.video_cache = None

    def _upload_video(self, info: VideoInfo) -> Message:
        try:
            v_msg = self.dispatcher.bot.send_video(
                self.dispatcher.devnullchat, open(info.filepath, "rb"), 
                filename=info.orig_filename
            )
            logging.debug(f"Video {info.orig_filename} uploaded successfully")
            return v_msg
        except TelegramError as err:
            logging.warn(f"Telegram Error occured: {err}")


from threading import Event, Thread
from multiprocessing import Process
from telegram import Bot, InlineQuery, InlineQueryResultCachedVideo, TelegramError, InlineQueryResultArticle, InputTextMessageContent
import logging
from typing import Optional
from yt_dlp.utils import YoutubeDLError
from dataclasses import dataclass

from resourcemanager import ResourceManager
from downloader import Downloader

from util import validate_query, clean_yt_error
from downloader import VideoInfo


@dataclass
class Query:
    event: Event
    process: Optional[Process]


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
            query = self._next_query_arrived_events[inline_query.from_user.id]
            query.event.set()
            # needing to terminate process as there is no trivial 
            # way to stop YoutubeDL during the download
            if query.process is not None:
                query.process.terminate()
        except KeyError:
            ...
        finally:
            self._next_query_arrived_events[inline_query.from_user.id] = Query(Event(), None)

        responder = Process(
            target=self._respondToInlineQuery,
            args=[inline_query, self._next_query_arrived_events[inline_query.from_user.id].event]
        )
        self._next_query_arrived_events[inline_query.from_user.id].process = responder
        responder.start()
        Thread(target=self.joinProcess, args=[responder, inline_query.query]).start()

    def joinProcess(self, process, query):
        logging.debug(f"Starting process - '{query}' {process}")
        process.join()
        logging.debug(f"Ending process - {process}")

    def _respondToInlineQuery(self, inline_query: InlineQuery, next_arrived_event: Event):
        query = inline_query.query
        query_id = inline_query.id

        if not validate_query(query):
            return

        try:
            if not next_arrived_event.is_set():
                info = self._downloader.download(query)
            if not next_arrived_event.is_set():
                result = self._upload_video(info, query)
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
            if not next_arrived_event.is_set():
                self._bot.answerInlineQuery(query_id, [result], cache_time=0)
                logging.debug(f"Answered to inline query '{query}'")

    def _upload_video(self, info: VideoInfo, url: str):
        try:
            v_msg = self._bot.send_video(
                self._devnullchat, open(info.filepath, "rb"), filename=info.orig_filename
            )

            media_id = v_msg.video.file_id

            logging.debug(f"Video {info.orig_filename} uploaded successfully")

            return InlineQueryResultCachedVideo(
                0, video_file_id=media_id, title=info.title, caption=url
            )

        except TelegramError as err:
            logging.warn(f"Telegram Error occured: {err}")


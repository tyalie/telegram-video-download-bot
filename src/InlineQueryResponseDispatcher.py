from threading import Event, Thread
from telegram import Bot, InlineQuery, InlineQueryResultCachedVideo, TelegramError
import logging

from resourcemanager import ResourceManager
from downloader import Downloader

from util import validate_query
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
            self._next_query_arrived_events[inline_query.from_user.id].set()
        except KeyError:
            ...
        finally:
            self._next_query_arrived_events[inline_query.from_user.id] = Event()

        Thread(
            target=self._respondToInlineQuery,
            args=[inline_query, self._next_query_arrived_events[inline_query.from_user.id]]
        ).start()

    def _respondToInlineQuery(self, inline_query: InlineQuery, next_arrived_event: Event):
        query = inline_query.query
        query_id = inline_query.id

        if not validate_query(query):
            return

        if not next_arrived_event.is_set():
            info = self._downloader.download(query)
        if not next_arrived_event.is_set():
            result = self._upload_video(info, query)
        if not next_arrived_event.is_set():
            self._bot.answerInlineQuery(query_id, [result])
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



        



import logging
from typing import Callable, Dict
from telegram import Update, TelegramError, Message
import tempfile
from telegram.utils.helpers import escape_markdown
from telegram.ext import (
    Updater, Dispatcher, CallbackContext, CommandHandler, 
    Filters, InlineQueryHandler
)

from yt_dlp.utils import YoutubeDLError
from downloader import Downloader 
from resourcemanager import resource_manager
from InlineQueryResponseDispatcher import InlineQueryRespondDispatcher
from util import clean_yt_error


class InlineBot:
    def __init__(self, token, devnullchat=-1):
        self._updater = Updater(token=token, use_context=True)

        self._inline_query_response_dispatcher = InlineQueryRespondDispatcher(
            self._updater.bot, devnullchat
        )

        _start = CommandHandler('start', self.on_start, filters=Filters.chat_type.private)
        self._dispatcher.add_handler(_start)

        _download = CommandHandler('download', self.on_download, run_async=True)
        self._dispatcher.add_handler(_download)

        _chat_id = CommandHandler('get_chat_id', self.get_chat_id)
        self._dispatcher.add_handler(_chat_id)

        self._dispatcher.bot.set_my_commands([
            (_download.command[0], "Download the video file from the given URL")
        ])

        self._dispatcher.add_handler(InlineQueryHandler(self.on_inline, run_async=True))

    @property
    def _dispatcher(self) -> Dispatcher:
        return self._updater.dispatcher

    def launch(self):
        self._updater.start_polling()

    def stop(self):
        self._updater.stop()

    def on_start(self, update: Update, context: CallbackContext):
        update.message.reply_text(resource_manager.get_string("greeting"))

    def get_chat_id(self, update: Update, context: CallbackContext):
        update.message.reply_text(f"{update.message.chat_id}")

    def _build_progress_handler(self, status_message: Message) -> Callable[[Dict], None]:
        last_bucket = None
        counter = 0

        def handler(data: Dict):
            nonlocal last_bucket, counter

            text = None
            if data["status"] == "finished":
                text = resource_manager.get_string("status_download_finished")
            elif data["status"] == "downloading":
                if "total_bytes" in data and "downloaded_bytes" in data:
                    progress = data["downloaded_bytes"] / data["total_bytes"] * 100

                    # I can't update message to often if it is in group
                    if status_message.chat.type == "private":
                        text = resource_manager.get_string(
                            "status_download_progress", progress=f"{progress:.1f}")
                else:
                    text = resource_manager.get_string("status_download_progress", progress='?')

            else:
                text = escape_markdown(f"Unknown status - {data['status']}")

            if text is not None and text != status_message.text:
                if counter < 5 or status_message.chat.type == "private":
                    status_message.edit_text(text, parse_mode='Markdown')
                    status_message.text = text
                    counter += 1

        return handler

    def on_download(self, update: Update, context: CallbackContext):
        if len(context.args) != 1:
            update.message.reply_text(resource_manager.get_string("download_error_arg_one"))
            return

        status_message = None

        try:
            status_message = update.message.reply_text(
                resource_manager.get_string("status_download_progress", progress="0"), 
                parse_mode="Markdown", reply_to_message_id=update.message.message_id
            )

            with Downloader() as downloader:
                info = downloader.start(
                    context.args[0], self._build_progress_handler(status_message)
                )

                logging.debug(f"Bot: Uploading file '{info.orig_filename}'")
                update.message.reply_video(
                    open(info.filepath, "rb"),
                    supports_streaming=True, reply_to_message_id=update.message.message_id,
                    filename=info.orig_filename, duration=info.duration_s
                )
        except TelegramError as err:
            logging.warn("Telegram error", exc_info=err)
            update.message.reply_markdown(
                resource_manager.get_string("error_telegram", error=err.message),
                reply_to_message_id=update.message.message_id
            )
        except YoutubeDLError as err:
            logging.info(f"Download error ({context.args[0]})")
            error_text = escape_markdown(clean_yt_error(err), version=2, entity_type="CODE")
            update.message.reply_markdown_v2(
                resource_manager.get_string("error_download", error=error_text),
                reply_to_message_id=update.message.message_id,
                disable_web_page_preview=True
            )
        finally:
            if status_message is not None:
                status_message.delete()

    def on_inline(self, update: Update, context: CallbackContext):
        query = update.inline_query.query

        if query == "":
            return

        self._inline_query_response_dispatcher.dispatchInlineQueryResponse(update.inline_query)

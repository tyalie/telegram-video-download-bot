import logging
from telegram import Update
from telegram.ext import (
    Updater, Dispatcher, CallbackContext, CommandHandler, 
    Filters, InlineQueryHandler
)

from downloader import Downloader 
from resourcemanager import ResourceManager
from InlineQueryResponseDispatcher import InlineQueryRespondDispatcher


class InlineBot:
    def __init__(self, token, devnullchat=-1):
        self._updater = Updater(token=token, use_context=True)
        self._downloader = Downloader()
        self._resource_man = ResourceManager()

        self._inline_query_response_dispatcher = InlineQueryRespondDispatcher(
            self._updater.bot, self._resource_man, self._downloader, devnullchat
        )

        _start = CommandHandler('start', self.on_start, filters=Filters.chat_type.private)
        self._dispatcher.add_handler(_start)

        _download = CommandHandler('download', self.on_download, run_async=True)
        self._dispatcher.add_handler(_download)

        _chat_id = CommandHandler('get_chat_id', self.get_chat_id, filters=Filters.chat_type.private)
        self._dispatcher.add_handler(_chat_id)

        self._dispatcher.add_handler(InlineQueryHandler(self.on_inline, run_async=True))

    @property
    def _dispatcher(self) -> Dispatcher:
        return self._updater.dispatcher

    def launch(self):
        self._updater.start_polling()

    def stop(self):
        self._updater.stop()

    def on_start(self, update: Update, context: CallbackContext):
        update.message.reply_text(self._resource_man.get_string("greeting"))

    def get_chat_id(self, update: Update, context: CallbackContext):
        update.message.reply_text(f"{update.message.chat_id}")

    def on_download(self, update: Update, context: CallbackContext):
        if len(context.args) != 1:
            update.message.reply_text(self._resource_man.get_string("download_error_arg_one"))
            return

        info = self._downloader.download(context.args[0])
        logging.debug(f"Bot: Uploading file '{info.orig_filename}'")
        update.message.reply_video(
            open(info.filepath, "rb"),
            supports_streaming=True, reply_to_message_id=update.message.message_id,
            filename=info.orig_filename, duration=info.duration_s
        )

    def on_inline(self, update: Update, context: CallbackContext):
        query = update.inline_query.query

        if query == "":
            return

        self._inline_query_response_dispatcher.dispatchInlineQueryResponse(update.inline_query)

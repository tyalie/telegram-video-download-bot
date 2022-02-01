import signal

from bot import InlineBot
from settings import config
from util import check_ffmpeg


def terminate(bot: InlineBot):
    def handler(signum, frame):
        print(f"TERMINATE with {signum}")
        bot.stop()
    return handler


def main():
    check_ffmpeg()

    token = config.token
    bot = InlineBot(token, devnullchat=config.dev_null_chat)
    signal.signal(signal.SIGTERM, terminate(bot))

    bot.launch()


if __name__ == "__main__":
    main()

from bot import InlineBot
from settings import config


def main():
    token = config.token
    bot = InlineBot(token)
    bot.launch()


if __name__ == "__main__":
    main()

from pydantic import BaseSettings
from pathlib import Path
import logging


class Settings(BaseSettings):
    token_path: Path = "./token"
    debug: bool = "False"

    bot_name: str = "Video Bot"
    bot_handle: str = "@something"

    max_video_length_s: int = 240
    resource_path: Path = Path(__file__).parent / "../resources"

    logging_mode: str = "INFO"
    dev_null_chat: int = -1

    debug_yt_traffic: bool = "False"
    yt_socket_timeout: float = "2"
    yt_quiet_mode: bool = "True"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        logging.basicConfig(level=self.logging_mode)
        logging.debug(f"Using RESOURCE_PATH: {self.resource_path}")

        if not config.bot_handle.startswith("@"):
            logging.warning(
                f"The bot handle should start with an '@' (currently: '{config.bot_handle}')")

    @property
    def token(self) -> str:
        assert self.token_path.is_file(), "No token provided"
        with open(self.token_path, "r") as f:
            return f.read().strip()

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'


config = Settings()

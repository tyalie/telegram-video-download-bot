from string import Template
from typing import Dict
from settings import config
import json


class ResourceManager():
    def __init__(self, strings_file=None):
        if strings_file is None:
            strings_file = config.resource_path / "strings.json"

        self.strings_file = strings_file

    def get_string(self, sid, **kwargs):
        """Get strings and put in placeholders"""
        return self._all_strings[sid].substitute(
            kwargs, botname=config.bot_name, bothandle=config.bot_handle
        )

    @property
    def _all_strings(self) -> Dict[str, Template]:
        """
        Only reread all strings on access if in debug mode. 
        Otherwise cache the result
        """
        try:
            data = self.__data_buffer
        except AttributeError:
            with open(self.strings_file, "r") as f:
                _data = json.load(f)

            data = {key: Template(value) for key, value in _data.items()}

            if not config.debug:
                self.__data_buffer = data
        finally:
            return data


resource_manager = ResourceManager()

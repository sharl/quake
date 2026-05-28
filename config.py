# -*- coding: utf-8 -*-
from pathlib import Path
import json
import os
import sys


class Config:
    def __init__(self, APP_NAME):
        # XDG_CONFIG_HOME
        self.path = Path.home().joinpath('.config', APP_NAME, 'config.json')

    def load(self) -> dict:
        try:
            with open(self.path, mode='r', encoding='utf-8') as fd:
                return json.load(fd)
        except Exception:
            return {}

    def save(self, data: dict) -> int:
        """
        return
        0: success
        -1: error
        """
        dirname = os.path.dirname(self.path)
        os.makedirs(dirname, exist_ok=True)

        try:
            with open(self.path, mode='w', encoding='utf-8') as fd:
                fd.write(json.dumps(data, ensure_ascii=False))
                return 0
        except Exception as e:
            print(e, file=sys.stderr)
        return -1

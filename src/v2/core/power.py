from .constants import PM_LIST
from .. import config

class Power:
    def __init__(self):
        self.default = if config.get_config("power.default") in PM_LIST else PM_ACTIVE

    def evaluate(self):
        pass

    def set_mode(self, mode):
        pass

    def get_mode(self) -> str:
        pass

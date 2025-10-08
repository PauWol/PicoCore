import uasyncio
from config import get_config
from logger import init_logger,get_logger
class Root:
    def __init__(self):
        pass

    def init(self):
        cfg = get_config()
        logger = cfg.get("system.logger")
        print(logger)

    def run(self):
        uasyncio.gather([])
from core.utils.utils import file_exists, create_bin_file, time_to_bytes, format_time, get_file_size, clear_bin_file, \
    rotate_file, append_bytes
from core.constants.constants import LOG_LEVELS, FILE_LOG, FILE_LOG_TEMP, FILE_DATA, FILE_DATA_TEMP, LOG_HDR_SOB, LOG_HDR_EOB, DATA_HDR_EDB, DATA_HDR_SDB, DATA_HDR_MDB, domain_to
#from core.utils.error import ErrorCodes
from core.utils.queue import QueueManager
from sys import modules
from time import time


class Log:
    def __init__(self, level:bytes=None, bufferSize=8, Max=50, file=True, console=True,error_handling=True):
        self.level = level if level is not None else LOG_LEVELS["INFO"]
        self._level_original = level
        self.file = file
        self.console = console
        self.error_handling = error_handling
        self.log_msg_overwrite = True

        self.queue_manager = QueueManager()
        self.queue_manager.register("logs", bufferSize, lambda b: append_bytes(FILE_LOG_TEMP, b))
        self.queue_manager.register("data", bufferSize, lambda b: append_bytes(FILE_DATA_TEMP, b))

        self.MAX_FILE_SIZE = Max * 8
        self.init()

    # -----------------------------------------------------
    # Initialize logging Files
    # -----------------------------------------------------

    @staticmethod
    def init():
        for file in [FILE_LOG, FILE_LOG_TEMP, FILE_DATA, FILE_DATA_TEMP]:
            if not file_exists(file):
                create_bin_file(file)

    @staticmethod
    def _is_level(level, target):
        return int.from_bytes(level, "big") <= int.from_bytes(target, "big")



    def _queue_data(self, data):
        self.queue_manager.put("data", data)
        self.flush(FILE_DATA, FILE_DATA_TEMP)

    def _queue_log(self, log_message):
        self.queue_manager.put("logs", log_message)
        self.flush(FILE_LOG, FILE_LOG_TEMP)

    def cleanup(self):
        self.queue_manager.flush_all()
        self.flush(FILE_DATA, FILE_DATA_TEMP)
        self.flush(FILE_LOG, FILE_LOG_TEMP)

    def _buildLog(self, level:str, domain: str, msg: str,origin:str=None):
        origin = origin if origin else "<unknown>"
        timestamp = time()
        log_entry = bytearray()
        log_entry.extend(LOG_LEVELS[level])
        log_entry.extend(time_to_bytes(timestamp))
        log_entry.extend(LOG_HDR_SOB+origin.encode("utf-8","ignore")+LOG_HDR_EOB)
        log_entry.extend(domain_to(domain,byte=True))
        log_entry.extend(msg.encode() if msg else b"")

        #if self.error_handling: TODO: implement error handling uncommented due to result in circular import
         #  ErrorCodes.handle(level, domain)

        if self.file:
            self._queue_log(log_entry)

        if self.console:
            return self._format(level, timestamp,origin,domain,msg)

        return ""

    @staticmethod
    def _format(level:str, timestamp:int,origin: (str,str,int) ,domain: str, msg:str):
        return f"[{level}] {format_time(timestamp)} ( {origin} | {domain} ) {msg}"

    def flush(self, name, name_temp, max_rotations=3):
        # Append temp -> main, clear temp, then rotate main if too large.
        try:
            # append temp contents
            if file_exists(name_temp):
                with open(name_temp, "rb") as temp_f:
                    data = temp_f.read()
                if data:
                    # append atomically
                    with open(name, "ab") as main_f:
                        main_f.write(data)
                # clear temp file
                clear_bin_file(name_temp)

            # rotate if the file is too large
            if get_file_size(name) > self.MAX_FILE_SIZE:
                rotate_file(name, max_rotations)
                # create a fresh main file to continue loging
                create_bin_file(name)

        except OSError as e:
            print(f"LOG ERROR: Failed to flush data - {e}")

    # -----------------------------------------------------
    # Public logging Functions
    # -----------------------------------------------------

    def debug(self, domain , msg="",origin:str=None):
        if self._is_level(self.level, LOG_LEVELS["DEBUG"]):
            log = self._buildLog("DEBUG", domain, msg,origin)
            if self.console:
                print(log)

    def info(self, domain, msg="",origin:str=None):
        if self._is_level(self.level, LOG_LEVELS["INFO"]):
            log = self._buildLog("INFO", domain, msg,origin)
            if self.console:
                print(log)

    def warn(self, domain, msg="",origin:str=None):
        if self._is_level(self.level, LOG_LEVELS["WARN"]):
            log = self._buildLog("WARN", domain, msg,origin)
            if self.console:
                print(log)

    def error(self, domain, msg="",origin:str=None):
        if self._is_level(self.level, LOG_LEVELS["ERROR"]):
            log = self._buildLog("ERROR", domain, msg,origin)
            if self.console:
                print(log)

    def fatal(self, domain, msg="",origin:str=None):
        if self._is_level(self.level, LOG_LEVELS["FATAL"]):
            log = self._buildLog("FATAL", domain, msg,origin)
            if self.console:
                print(log)

    # -----------------------------------------------------
    # Public Data Functions
    # -----------------------------------------------------

    def data(self, data_name:str,data:str):
        self._queue_data(DATA_HDR_SDB + data_name.encode() + DATA_HDR_MDB + data.encode() + DATA_HDR_EDB)

    # -----------------------------------------------------
    # System Health Control to limit logs if storage is low
    # -----------------------------------------------------

    def mode(self, mode="normal"):
        if mode == "low":
            self.level = LOG_LEVELS["WARN"]
            self.log_msg_overwrite = False
        elif mode == "medium":
            self.level = LOG_LEVELS["WARN"]
        elif mode == "normal":
            self.log_msg_overwrite = True
            self.level = self._level_original



if not hasattr(modules[__name__], "logger_instance"):
    # print("[PicoOS] Logger Singleton Created")
    logger_instance: Log | None = None


def get_logger():
    return logger_instance


if __name__ == "__main__":
    from core.constants.constants import BOARD_TEMP
    logger_instance = Log()
    logger_instance.mode("low")
    logger_instance.info(BOARD_TEMP, "This is a test temp is normal",origin="test")
    logger_instance.error(BOARD_TEMP, "This is a test temp too high",origin="test")


"""
PicoCore V2 Logger Class

Logger class for logging messages to console and file.As well as application data entries.

Usage:
    from core.logging import logger

    logger = Logger()
    logger.info("Hello World")
    logger.data("test", "Hello World")
"""

import os
import ustruct

from ..constants import TRACE , INFO , DEBUG , FATAL , ERROR , WARN , LEVEL_NAMES , LOG_FILE_PATH , DATA_FILE_PATH , LEVEL_BYTES , LOGGER_LEVEL ,\
LOGGER_BUFFER_SIZE , LOGGER_MAX_FILE_SIZE , LOGGER_CONSOLE , LOGGER_FILE_LOG , LOGGER_MAX_ROTATIONS , LEVEL_NAMES_REV
from ..config import get_config
from ..util import _file_exists , uptime , create_file
from ..queue import RingBuffer , ByteRingBuffer


class Logger:
    def __init__(self,level:int=INFO, buffer_size:int=5, max_file_size:int|str="64kb", console:bool=True, file_log:bool=True, max_rotations:int=3):
        """
         Logger class for logging messages to console and file.As well as application data entries.
         :param level: Can be TRACE, DEBUG, INFO, WARN, ERROR, FATAL  as int-> (0,1,2,3,4,5) use constants for best efficiency
         :param buffer_size: The size of the log buffer/ data buffer if full the logs/data will be flushed to disk. (45 bytes per log entry; buffer_size * 45 bytes)
         :param max_file_size: The maximum size of the log- / datafile before it is rotated.
         :param console: Weather logs should be printed to console
         :param file_log: Weather logs should be written to file
         :param max_rotations: The maximum number of log- / datafiles before the oldest is deleted
         :return:
         """
        self.level = level
        self.buffer_size = buffer_size # 45 bytes per log entry
        self.console = console
        self.file_log = file_log
        self.max_bytes = self._parse_size(max_file_size)
        self.max_rotations = max_rotations

        # runtime
        self._orig_level = self.level
        self._log_buf = ByteRingBuffer(self.buffer_size * 45 )
        self._data_buf = RingBuffer(self.buffer_size,True)

        self.log_path = LOG_FILE_PATH
        self.data_path = DATA_FILE_PATH
        self._file_checks()

    def _file_checks(self) -> None:
        """
        Check if the log file exists and create it if it doesn't.
        """
        if not _file_exists(self.log_path) and self.file_log:
            create_file(self.log_path)

    @staticmethod
    def _parse_size(size: str | int) -> int:
        """
        Parse an int or string (e.g. "64kb") into bytes.
        :param size: Either int as byte or string with suffix ("1b" , "1kb" , "1mb")
        :return:
        """
        if isinstance(size, int):
            return size

        size = size.strip().lower()
        if size.endswith("kb"):
            return int(size[:-2]) * 1024
        if size.endswith("mb"):
            return int(size[:-2]) * 1024 * 1024
        if size.endswith("b"):
            return int(size[:-1])
        raise ValueError("Invalid size string")

    @staticmethod
    def _timestamp() -> int:
        """
        Get the current time in milliseconds.
        :return:
        """
        return uptime(ms=True)

    @staticmethod
    def _format_timestamp(t:int) -> str:
        """
        Format a timestamp in a human-readable format.
        :param t:
        :return:
        """
        total_s, _ = divmod(t, 1000)
        m, s = divmod(total_s, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        return f"{d}d {h:02}:{m:02}:{s:02}"

    @staticmethod
    def _format_line_bin(t:int, level_int:int, msg:str) -> bytes:
        """
        Format a log line with timestamp, level and message. -> Binary format
        :param t:
        :param level_int:
        :param msg:
        :return:
        """
        lvl = LEVEL_BYTES.get(level_int)
        t =  ustruct.pack('<I', t)
        msg = msg.encode("utf-8")
        return lvl + t + msg

    def _format_line(self,t:int, level_int:int, msg:str) -> str:
        """
        Format a log line with timestamp, level and message. -> Readable format
        :param t:
        :param level_int:
        :param msg:
        :return:
        """
        lvl = LEVEL_NAMES.get(level_int)
        t = self._format_timestamp(t)
        return f"{t} | {lvl} | {msg} \n"


    def _enqueue_log(self, level_int, msg):
        """
        Enqueue log to be logged.
        :param level_int:
        :param msg:
        """
        if not self.file_log and not self.console:
            return

        t = self._timestamp()

        if self.console:
            line = self._format_line(t, level_int, msg)
            print(line.rstrip("\n"))

        if self.file_log:
            line_b = self._format_line_bin(t, level_int, msg)
            self._log_buf.put(line_b)

            # flush immediate if buffer full
            if self._log_buf.is_full():
                self._flush_logs()

    def _enqueue_data(self, name, data_str):
        """
        Enqueue data to be logged.
        :param name:
        :param data_str:
        """
        line = f"{self._timestamp()},{name},{data_str}\n"
        self._data_buf.put(line)
        if self._data_buf.is_full():
            self._flush_data()

    def _flush_logs(self):
        """Write buffered log lines to disk and rotate if needed. Small-chunk write only."""
        if not _file_exists(self.log_path):
            create_file(self.log_path)

        if self._log_buf.is_empty():
            return

        try:
            with open(self.log_path, 'ab') as f:
                    f.write(self._log_buf.to_bytes())
            self._log_buf.clear()
            self._rotate_if_needed(self.log_path)
        except OSError as e:
            print(f"Error writing to file: {e}")

    def _flush_data(self):
        """Write buffered data lines to disk and rotate if needed."""
        if not _file_exists(self.data_path):
            create_file(self.data_path)

        if self._data_buf.is_empty():
            return

        try:
            with open(self.data_path, "a", encoding="utf-8") as f:
                for i in self._data_buf:
                    f.write(i)

            self._data_buf.clear()
            self._rotate_if_needed(self.data_path)
        except OSError as e:
                print("[LOGGER] flush_data OSError:", e)

    def flush(self):
        """Flush both buffers"""
        self._flush_logs()
        self._flush_data()

    def _rotate_if_needed(self, path):
        size = os.stat(path)[6] if len(os.stat(path)) > 6 else os.stat(path).st_size

        if size:
            size = os.stat(path)[0]
        else:
            size = 0

        if self.max_bytes <= 0:
            return

        if size > self.max_bytes:
            # rotate: path -> path.0, path.0 -> path.1 ... up to max_rotations-1
            try:
                # remove oldest if needed
                last = f"{path}.{self.max_rotations - 1}"
                if _file_exists(last):
                        os.remove(last)
                for i in range(self.max_rotations - 2, -1, -1):
                    src = f"{path}.{i}" if i > 0 else path
                    dst = f"{path}.{i + 1}"
                    if _file_exists(src):
                            os.rename(src, dst)
            except OSError as e:
                print("[LOGGER] _rotate_if_needed Exception",e)

    def _should_log(self, level_int:int):
        return level_int <= self.level

    def trace(self, msg="") -> None:
        """
        Log some trace information.
        :param msg:
        :return:
        """
        if self._should_log(TRACE):
            self._enqueue_log(TRACE, msg)

    def debug(self, msg="") -> None:
        """
        Log some debug information.
        :param msg:
        :return:
        """
        if self._should_log(DEBUG):
            self._enqueue_log(DEBUG, msg)

    def info(self, msg="") -> None:
        """
        Log some information.
        :param msg:
        :return:
        """
        if self._should_log(INFO):
            self._enqueue_log(INFO, msg)

    def warn(self, msg="") -> None:
        """
        Log a warning.
        :param msg:
        :return:
        """
        if self._should_log(WARN):
            self._enqueue_log(WARN, msg)
            self._flush_logs()

    def error(self, msg="") -> None:
        """
        Log a normal error.
        :param msg:
        :return:
        """
        if self._should_log(ERROR):
            self._enqueue_log(ERROR, msg)
            self._flush_logs()

    def fatal(self, msg="") -> None:
        """
        Log a fatal error.
        :param msg:
        :return:
        """
        if self._should_log(FATAL):
            self._enqueue_log(FATAL, msg)
            self._flush_logs()

    def data(self, name, data_str) -> None:
        """
        Log application data.
        :param name:
        :param data_str:
        :return:
        """
        self._enqueue_data(name, data_str)

    def mode(self, mode_name="normal") -> None:
        """
        Change loging mode:
          - 'low'  -> WARN only, no overwrites
          - 'medium' -> WARN
          - 'normal' -> restore original
        """
        if mode_name == "low":
            self.level = WARN
        elif mode_name == "medium":
            self.level = WARN
        elif mode_name == "normal":
            self.level = self._orig_level

    def get_status(self) -> dict:
        """
        Return the current status of the logger.
        :return: dict with current status (level, queue_len, data_queue_len, file_log, console)
        """
        return {
            "level": self.level,
            "queue_len": len(self._log_buf),
            "data_queue_len": len(self._data_buf),
            "file_log": self.file_log,
            "console": self.console
        }

_logger_instance: Logger | None = None

def init_logger(level=INFO,buffer_size=5,max_file_size="64kb",console=True,file_log=True,max_rotations=3) -> Logger:
    """
    Initialize the global logger singleton.
    :param level: Can be TRACE, DEBUG, INFO, WARN, ERROR, FATAL  as int-> (0,1,2,3,4,5) use constants for best efficiency
    :param buffer_size: The size of the log buffer/ data buffer if full the logs/data will be flushed to disk.
    :param max_file_size: The maximum size of the log- / datafile before it is rotated.
    :param console: Weather logs should be printed to console
    :param file_log: Weather logs should be written to file
    :param max_rotations: The maximum number of log- / datafiles before the oldest is deleted
    :return:
    """
    global _logger_instance # pylint: disable=global-statement
    if _logger_instance is None:
        cfg = get_config()
        _logger_instance = Logger(
            level=LEVEL_NAMES_REV.get(cfg.get(LOGGER_LEVEL)) or level,
            buffer_size=cfg.get(LOGGER_BUFFER_SIZE) or buffer_size,
            max_file_size=cfg.get(LOGGER_MAX_FILE_SIZE) or max_file_size,
            console=cfg.get(LOGGER_CONSOLE) or console,
            file_log=cfg.get(LOGGER_FILE_LOG) or file_log,
            max_rotations=cfg.get(LOGGER_MAX_ROTATIONS) or max_rotations
        )
    return _logger_instance

def logger() -> Logger:
    """Return the global Logger instance (must call init_logger first."""
    if _logger_instance is None:
        raise RuntimeError("Logger not initialized. Call init_logger() first.")
    return _logger_instance


# TODO: Better data loging logic
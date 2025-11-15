from ..constants import OFF , INFO , DEBUG , FATAL , ERROR , WARN , LEVEL_NAMES
from ..util import _file_exists , uptime , create_file
import os



class Logger:
    """
    Lightweight MicroPython-friendly logger with:
      - level filtering (ints)
      - in-memory batching + periodic flush
      - rotation by size
      - console & file output
      - simple data stream method
    """

    def __init__(self,
                 level=INFO,
                 buffer_size=5,
                 max_file_size_kb=64,
                 file_path="logs.txt",
                 data_path="data.txt",
                 console=True,
                 file_log=True,
                 max_rotations=3):
        # config
        self.level = int(level)
        self._orig_level = int(level)
        self.buffer_size = int(buffer_size)
        self.file_path = file_path
        self.data_path = data_path
        self.console = bool(console)
        self.file_log = bool(file_log)
        self.max_bytes = int(max_file_size_kb) * 1024
        self.max_rotations = int(max_rotations)

        # runtime
        self._log_buf = []  # list of bytes or strings to write to log file
        self._data_buf = []

        self._file_checks()

    # -------------------------
    # Internal util
    # -------------------------

    def _file_checks(self):
        if not _file_exists(self.file_path):
            create_file(self.file_path)
        if not _file_exists(self.data_path):
            create_file(self.data_path)

    @staticmethod
    def _timestamp() -> int:
        return uptime(formatted=True)

    def _format_line(self, level_int, domain, origin, msg):
        # Simple human readeble line: ISO-ish timestamp | LEVEL | origin | domain | msg\n
        t = self._timestamp()
        lvl = LEVEL_NAMES.get(level_int, str(level_int))
        origin = origin if origin is not None else "<unknown>"
        # keep single string and encode once when writing to file
        return f"{t} | {lvl} | {origin} | {domain} |{msg} \n"

    # -------------------------
    # Buffer & flush logic
    # -------------------------
    def _enqueue_log(self, level_int, domain, msg, origin):
        if not self.file_log and not self.console:
            return
        line = self._format_line(level_int, domain, origin, msg)
        # console immediate print (non-blocking)
        if self.console:
                print(line.rstrip("\n"))
        if self.file_log:
            self._log_buf.append(line)
            # flush immediate if buffer full
            if len(self._log_buf) >= self.buffer_size:
                # sync flush; if running under asyncio, the flusher loop will handle it anyway
                self.flush_logs()

    def _enqueue_data(self, name, data_str):
        line = f"{self._timestamp()}|{name}|{data_str}\n"
        if self.file_log:
            self._data_buf.append(line)
            if len(self._data_buf) >= self.buffer_size:
                self.flush_data()

    def flush_logs(self):
        """Write buffered log lines to disk and rotate if needed. Small-chunk write only."""
        if not self.file_log:
            # nothing to do
            self._log_buf.clear()
            return
        if not self._log_buf:
            return
        try:
            with open(self.file_path, "ab") as f:
                for line in self._log_buf:
                    # encode and write
                    try:
                        f.write(line.encode("utf-8"))
                    except Exception:
                        # fallback to ascii safe
                        f.write(line.encode("ascii", "ignore"))
            self._log_buf.clear()
            # check rotation
            self._rotate_if_needed(self.file_path)
        except OSError as e:
            # On error, disable file loging to avoid busy failures
            self.file_log = False
            if self.console:
                print("[LOGGER] flush_logs OSError:", e)

    def flush_data(self):
        if not self.file_log:
            self._data_buf.clear()
            return
        if not self._data_buf:
            return
        try:
            with open(self.data_path, "ab") as f:
                for line in self._data_buf:
                    try:
                        f.write(line.encode("utf-8"))
                    except Exception:
                        f.write(line.encode("ascii", "ignore"))
            self._data_buf.clear()
            self._rotate_if_needed(self.data_path)
        except OSError as e:
            self.file_log = False
            if self.console:
                print("[LOGGER] flush_data OSError:", e)

    def flush(self):
        """Flush both buffers"""
        self.flush_logs()
        self.flush_data()

    def _rotate_if_needed(self, path):
        try:
            size = os.stat(path)[6] if len(os.stat(path)) > 6 else os.stat(path).st_size
        except Exception:
            # some ports return tuple different shapes; use try/except
            try:
                size = os.stat(path)[0]
            except Exception:
                size = 0
        if self.max_bytes <= 0:
            return
        if size > self.max_bytes:
            # rotate: path -> path.0, path.0 -> path.1 ... up to max_rotations-1
            try:
                # remove oldest if needed
                last = f"{path}.{self.max_rotations - 1}"
                if _file_exists(last):
                    try:
                        os.remove(last)
                    except Exception:
                        pass
                for i in range(self.max_rotations - 2, -1, -1):
                    src = f"{path}.{i}" if i > 0 else path
                    dst = f"{path}.{i + 1}"
                    if _file_exists(src):
                        try:
                            os.rename(src, dst)
                        except Exception:
                            # best effort; skip if cannot rename
                            pass
                # create a fresh empty main file
                try:
                    open(path, "wb").close()
                except Exception:
                    pass
            except Exception:
                # rotation failed; keep loging appends (best effort)
                pass

    # -------------------------
    # Public log API
    # -------------------------
    def _should_log(self, level_int):
        return level_int <= self.level

    def debug(self, domain, msg="", origin=None):
        if self._should_log(DEBUG):
            self._enqueue_log(DEBUG, domain, msg, origin)

    def info(self, domain, msg="", origin=None):
        if self._should_log(INFO):
            self._enqueue_log(INFO, domain, msg, origin)

    def warn(self, domain, msg="", origin=None):
        if self._should_log(WARN):
            self._enqueue_log(WARN, domain, msg, origin)

    def error(self, domain, msg="", origin=None):
        if self._should_log(ERROR):
            self._enqueue_log(ERROR, domain, msg, origin)

    def fatal(self, domain, msg="", origin=None):
        if self._should_log(FATAL):
            self._enqueue_log(FATAL, domain, msg, origin)

    def data(self, name, data_str):
        # lightweight wrapper for application data entries
        self._enqueue_data(name, data_str)

    # -------------------------
    # modes & status
    # -------------------------
    def mode(self, mode_name="normal"):
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

    def get_status(self):
        return {
            "level": self.level,
            "queue_len": len(self._log_buf),
            "data_queue_len": len(self._data_buf),
            "file_log": self.file_log,
            "console": self.console
        }


_logger_instance: Logger | None = None


def init_logger(
        level=INFO,
        buffer_size=5,
        max_file_size_kb=64,
        file_path="logs.txt",
        data_path="data.txt",
        console=True,
        file_log=True,
        max_rotations=3,
) -> Logger:
    """
    Initialize the global logger singleton and start background flush.
    Returns the Logger instance.
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = Logger(
            level=level,
            buffer_size=buffer_size,
            max_file_size_kb=max_file_size_kb,
            file_path=file_path,
            data_path=data_path,
            console=console,
            file_log=file_log,
            max_rotations=max_rotations,
        )
    return _logger_instance


def logger() -> Logger:
    """Return the global Logger instance (must call init_logger first."""
    if _logger_instance is None:
        raise RuntimeError("Logger not initialized. Call init_logger() first.")
    return _logger_instance

def _flusher_task():
        logger().flush()

#TODO: Review the flaws of this module
from typing import Any, Iterator, Optional
import os

from ..util import _file_exists, create_file
from ..constants import MAX_KEYS
from ..queue import RingBuffer


# Small chunk size for streaming-copy (keep low for constrained RAM)
_COPY_CHUNK = 512


class CSV:
    """
    MicroPython-optimized CSV helper.
    - Low-ram streaming for header updates (temp file + rename).
    - Minimal allocations when writing rows.
    - API: init(), get_headers(), write(key, value), write_row(dict), iter_rows(), clear()
    """

    def __init__(self, file_name: str, max_keys: int = MAX_KEYS):
        self.file_name = file_name
        self._max_keys = max_keys
        self._header_buffer = RingBuffer(self._max_keys)
        # lazily initialized flag
        self._inited = False

    # -----------------------
    # init / headers helpers
    # -----------------------
    def init(self) -> None:
        """Ensure file exists and load headers if present."""
        if self._inited:
            return

        if not _file_exists(self.file_name):
            create_file(self.file_name)
        else:
            # populate header buffer from file
            self._get_headers()
        self._inited = True

    def _is_header(self, header: str) -> bool:
        return header in self._header_buffer

    def get_headers(self) -> tuple[str, ...] | None:
        """Return tuple of headers (or None if none)."""
        return self._get_headers()

    def _get_headers(self) -> Optional[tuple]:
        """Parse first line into headers and populate ringbuffer. Minimal allocations."""
        if not self._header_buffer.is_empty():
            return self._header_buffer.to_tuple()

        try:
            f = open(self.file_name, "r")
        except OSError:
            return None

        try:
            line = f.readline()
            if not line:
                return None
            line = line.rstrip("\r\n")

            # manual split to avoid list-of-lists cost from repeated operations
            fields = []
            start = 0
            length = len(line)
            for _ in range(length + 1):
                idx = line.find(",", start)
                if idx == -1:
                    fields.append(line[start:])
                    break
                fields.append(line[start:idx])
                start = idx + 1

            headers = tuple(fields)
            self._set_headers(headers)
            return headers
        finally:
            f.close()

    def _set_headers(self, headers: tuple[str, ...]) -> None:
        """Extend ring buffer with headers (in one shot)."""
        self._header_buffer.extend(headers)

    def _add_header(self, header: str) -> None:
        self._header_buffer.put(header)

    # -----------------------
    # header write (safe)
    # -----------------------
    def _write_header(self, header: str | list[str] | tuple[str, ...]) -> None:
        """
        Safely add header(s). Implements streaming copy:
         - reads original file,
         - writes new header line to temp,
         - streams remainder in chunks to temp,
         - atomically replaces original with temp.
        This avoids loading entire file into RAM.
        """
        # normalize to iterator of strings
        if isinstance(header, str):
            it = (header,)
        else:
            it = header

        # gather only headers that are new (and reserve them into buffer as we go)
        new_buf = []
        for h in it:
            # skip duplicates and None/empty names
            if not h:
                continue
            if self._is_header(h):
                continue
            new_buf.append(h)
            # don't add to internal buffer yet — only after write success

        if not new_buf:
            return

        # read original header line (if any) and build new header line
        try:
            src = open(self.file_name, "r")
        except OSError:
            return None

        # create temp path in same dir
        tmp_path = self.file_name + ".tmp"
        try:
            dst = open(tmp_path, "w")
        except OSError:
            src.close()
            return None

        try:
            orig_first = src.readline()
            if not orig_first:
                # empty file -> new header line only
                dst.write(",".join(self._header_buffer.to_tuple() + tuple(new_buf)) if not self._header_buffer.is_empty() else ",".join(new_buf))
                dst.write("\n")
            else:
                orig_first = orig_first.rstrip("\r\n")
                # current headers may not be in buffer if _get_headers wasn't called earlier (ensure)
                if self._header_buffer.is_empty():
                    # parse existing first-line headers into buffer (cheap)
                    parts = []
                    start = 0
                    length = len(orig_first)
                    for _ in range(length + 1):
                        idx = orig_first.find(",", start)
                        if idx == -1:
                            parts.append(orig_first[start:])
                            break
                        parts.append(orig_first[start:idx])
                        start = idx + 1
                    self._set_headers(tuple(parts))

                # produce new header line (existing headers + new ones)
                # avoid creating huge temporaries: get existing headers from buffer
                existing = self._header_buffer.to_tuple()
                # join only once
                new_hdr_line = ",".join(existing + tuple(new_buf)) if existing else ",".join(new_buf)
                dst.write(new_hdr_line + "\n")

                # now stream the remainder of the original file in small chunks
                while True:
                    chunk = src.read(_COPY_CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
        finally:
            src.close()
            dst.close()

        # atomically replace original file
        try:
            os.remove(self.file_name)
        except OSError:
            # if remove fails, try rename/replace anyway (platform differences)
            pass
        try:
            os.rename(tmp_path, self.file_name)
        except OSError:
            # best-effort fallback: try replace if available
            try:
                os.replace(tmp_path, self.file_name)
            except Exception:
                # If replace fails, attempt to remove temp and keep original
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                raise

        # finally update internal buffer with the newly added headers
        for h in new_buf:
            self._add_header(h)

    # -----------------------
    # CSV quoting helper
    # -----------------------
    @staticmethod
    def _escape_field(val: Any) -> str:
        """
        Minimal CSV escaping:
        - if value contains comma, newline or quote -> quote the field and double quotes inside.
        - None -> empty
        """
        if val is None:
            return ""
        s = str(val)
        if not s:
            return ""
        # quick test: only do replace if necessary
        if ('"' in s) or (',' in s) or ('\n' in s) or ('\r' in s):
            # double quotes inside
            s = s.replace('"', '""')
            return '"' + s + '"'
        return s

    # -----------------------
    # write API
    # -----------------------
    def write(self, key: str, value: Any) -> None:
        """
        Append a new row where the column `key` contains `value` and other columns are empty.
        If `key` doesn't exist it'll be added to the header (streaming, safe).
        This keeps operations low-memory by streaming the line to disk.
        """
        self.init()

        if not self._is_header(key):
            # will update file safely and update buffer
            self._write_header(key)

        # Open append mode (create if missing)
        try:
            f = open(self.file_name, "a")
        except OSError:
            return None

        try:
            headers = self._header_buffer.to_tuple()
            # Build and write row directly without building a list of all fields
            # Write first field (no leading comma), then subsequent with comma prefix
            first = True
            for h in headers:
                if first:
                    first = False
                else:
                    f.write(",")
                if h == key:
                    f.write(self._escape_field(value))
                else:
                    # empty field -> nothing (keeps small)
                    # write nothing (i.e., leave empty between commas)
                    pass
            f.write("\n")
        finally:
            f.close()

    def write_row(self, row: dict[str, Any]) -> None:
        """
        Append a row given by a dict mapping header->value.
        Ensures missing headers are added first (safe streaming).
        """
        self.init()

        # collect new headers (iterate keys once)
        new_headers = []
        for k in row.keys():
            if not self._is_header(k):
                new_headers.append(k)

        if new_headers:
            self._write_header(new_headers)

        # open append and stream row
        try:
            f = open(self.file_name, "a")
        except OSError:
            return None

        try:
            headers = self._header_buffer.to_tuple()
            first = True
            for h in headers:
                if first:
                    first = False
                else:
                    f.write(",")
                v = row.get(h)
                if v is not None:
                    f.write(self._escape_field(v))
            f.write("\n")
        finally:
            f.close()

    # -----------------------
    # read API
    # -----------------------
    def iter_rows(self) -> Iterator[dict]:
        """
        Iterate rows as dictionaries mapping header->value.
        This is a streaming reader: reads file line by line, splits by comma (simple).
        Note: does not fully implement complex CSV quoting rules for multi-line quoted fields.
        """
        self.init()
        headers = self._get_headers()
        if not headers:
            return
        try:
            f = open(self.file_name, "r")
        except OSError:
            return

        try:
            # skip first line (headers)
            _ = f.readline()
            for raw in f:
                raw = raw.rstrip("\r\n")
                # simple split (fast). For heavy quoting needs, replace with a streaming parser.
                parts = []
                start = 0
                length = len(raw)
                i = 0
                while i < length:
                    # naive fast parse: split on comma; don't handle quoted commas here to keep memory/time low.
                    j = raw.find(",", i)
                    if j == -1:
                        parts.append(raw[i:])
                        break
                    parts.append(raw[i:j])
                    i = j + 1

                # map parts to headers (missing fields -> "")
                row = {}
                for idx, h in enumerate(headers):
                    row[h] = parts[idx] if idx < len(parts) else ""
                yield row
        finally:
            f.close()

    # -----------------------
    # utilities
    # -----------------------
    def clear(self) -> None:
        """Truncate file and clear header buffer."""
        try:
            f = open(self.file_name, "w")
            f.truncate(0)
            f.close()
        except OSError:
            pass
        # clear ringbuffer (recreate to avoid iterating clear)
        self._header_buffer = RingBuffer(self._max_keys)
        self._inited = False

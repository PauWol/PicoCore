import os

from core.util import _file_exists, create_file
from core.constants import MAX_KEYS
from core.queue import RingBuffer


# Small chunk size for streaming-copy (keep low for constrained RAM)
_COPY_CHUNK = 512


class SchemaLockedError(Exception):
    """Raised when attempting to add a new column to a schema-locked CSV."""


class CSV:
    """
    MicroPython-optimized CSV helper for PicoCore.

    Designed for RP2040-class hardware: every operation streams data
    rather than loading the file into RAM. Header updates use an atomic
    temp-file swap. Writes append directly without re-reading the file.

    Features
    --------
    - RFC 4180-compliant field parsing and escaping (shared _split_line helper)
    - Context manager  (``with CSV(...) as csv:``)
    - Schema locking   (freeze columns after first write — ideal for sensor logs)
    - Streaming reads  iter_rows(), find_rows(), get_last_n_rows()
    - Optional auto-cast of int / float values on read (``cast=True``)
    - count_rows()     without loading any row data into RAM

    Quick-start
    -----------
    .. code-block:: python

        # Sensor logging — fixed schema
        with CSV("sensors.csv") as csv:
            csv.schema_lock()
            csv.write_row({"ts": uptime(), "temp": 23.5, "hum": 60})

        # Read last 10 readings as typed values
        for row in csv.get_last_n_rows(10, cast=True):
            print(row["temp"])          # float, not str

        # Filter by sensor id
        for row in csv.find_rows("sensor_id", "A1"):
            print(row)

    Public API
    ----------
    init()                          Lazy setup (called automatically).
    get_headers()                   Tuple of column names, or None.
    schema_lock() / schema_unlock() Freeze / unfreeze columns.
    write(key, value)               Append a sparse row (one column set).
    write_row(dict)                 Append a full row from a mapping.
    iter_rows(cast=False)           Stream all rows as dicts.
    find_rows(key, value, cast)     Stream rows matching a filter.
    get_last_n_rows(n, cast)        Return the last n rows as a list.
    count_rows()                    Count data rows (streaming, no alloc).
    clear()                         Truncate file and reset state.
    """

    def __init__(self, file_name: str, max_keys: int = MAX_KEYS):
        self.file_name = file_name
        self._max_keys = max_keys
        self._header_buffer = RingBuffer(self._max_keys)
        self._inited = False
        self._schema_locked = False

    # ------------------------------------------------------------------ #
    # Context manager                                                      #
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "CSV":
        """Call init() on enter so the file is ready inside the block."""
        self.init()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # No persistent resources to release.
        # Return False so any exception propagates normally.
        return False

    # ------------------------------------------------------------------ #
    # Init / header helpers                                                #
    # ------------------------------------------------------------------ #

    def init(self) -> None:
        """
        Ensure the file exists and populate the header buffer from disk.
        Idempotent — safe to call multiple times; work only runs once.
        """
        if self._inited:
            return
        if not _file_exists(self.file_name):
            create_file(self.file_name)
        else:
            self._get_headers()
        self._inited = True

    def _is_header(self, header: str) -> bool:
        return header in self._header_buffer

    def get_headers(self) -> tuple[str, ...] | None:
        """Return a tuple of current column names, or None if the file is empty."""
        return self._get_headers()

    def _get_headers(self):
        """
        Parse the first line into headers and populate the ring buffer.
        Uses _split_line so quoted header names are handled correctly.
        """
        if not self._header_buffer.is_empty():
            return self._header_buffer.to_tuple()

        try:
            f = open(self.file_name)
        except OSError:
            return None

        try:
            line = f.readline()
            if not line:
                return None
            headers = tuple(self._split_line(line.rstrip("\r\n")))
            self._set_headers(headers)
            return headers
        finally:
            f.close()

    def _set_headers(self, headers: tuple[str, ...]) -> None:
        """Bulk-load headers into the ring buffer in one pass."""
        self._header_buffer.extend(headers)

    def _add_header(self, header: str) -> None:
        self._header_buffer.put(header)

    # ------------------------------------------------------------------ #
    # Schema lock                                                          #
    # ------------------------------------------------------------------ #

    def schema_lock(self) -> None:
        """
        Lock the column schema.

        Any subsequent write() or write_row() call that would introduce a
        new column raises SchemaLockedError instead of silently expanding
        the header line.  Best called once at boot after the first row has
        been written (or after init() if headers already exist on disk).

        Example::

            csv.init()
            csv.schema_lock()
            csv.write_row({"ts": 0, "temp": 0})  # OK — columns exist
            csv.write_row({"ts": 1, "new_col": 5})  # raises SchemaLockedError
        """
        self._schema_locked = True

    def schema_unlock(self) -> None:
        """Re-enable dynamic column addition."""
        self._schema_locked = False

    # ------------------------------------------------------------------ #
    # RFC 4180 line parser                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _split_line(line: str) -> list[str]:
        """
        Parse one CSV line into fields, RFC 4180-compliant.

        Handles:
        - Quoted fields that contain commas  ("hello, world" -> one field)
        - Escaped quotes inside quoted fields  ("say ""hi"" -> say "hi")
        - Trailing empty fields  ("a,b," -> ["a", "b", ""])
        - Unquoted fields (normal case, fast path)

        No regex, minimal allocations — suitable for RP2040.
        """
        fields = []
        field_chars = []
        i = 0
        length = len(line)

        while i < length:
            ch = line[i]

            if ch == '"':
                # --- Quoted field ---
                i += 1
                while i < length:
                    c = line[i]
                    if c == '"':
                        if i + 1 < length and line[i + 1] == '"':
                            # Escaped double-quote: "" -> "
                            field_chars.append('"')
                            i += 2
                        else:
                            # Closing quote
                            i += 1
                            break
                    else:
                        field_chars.append(c)
                        i += 1
                # Skip any garbage between closing quote and next comma
                while i < length and line[i] != ",":
                    i += 1

            elif ch == ",":
                fields.append("".join(field_chars))
                field_chars = []
                i += 1
                # A trailing comma means there is one more empty field
                if i == length:
                    fields.append("")

            else:
                # --- Unquoted character (common fast path) ---
                field_chars.append(ch)
                i += 1

        # Append the final field (covers both normal end and the no-comma case)
        fields.append("".join(field_chars))
        return fields

    # ------------------------------------------------------------------ #
    # RFC 4180 field escaping                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _escape_field(val) -> str:
        """
        Escape a value for writing into a CSV cell (RFC 4180).

        - None or empty string  ->  empty field (no output)
        - Values containing comma, newline, or double-quote are wrapped
          in double-quotes; internal quotes are doubled.
        """
        if val is None:
            return ""
        s = str(val)
        if not s:
            return ""
        if ('"' in s) or ("," in s) or ("\n" in s) or ("\r" in s):
            return '"' + s.replace('"', '""') + '"'
        return s

    # ------------------------------------------------------------------ #
    # Optional value casting                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cast(value: str):
        """
        Try to convert a string to int, then float, then return as-is.
        Only called when cast=True is passed to a read method — zero cost
        otherwise.

        Examples:
            "42"    -> 42   (int)
            "3.14"  -> 3.14 (float)
            "hello" -> "hello"
            ""      -> ""
        """
        if not value:
            return value
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    # ------------------------------------------------------------------ #
    # Safe streaming header update                                         #
    # ------------------------------------------------------------------ #

    def _write_header(self, header: str | list[str] | tuple[str, ...]) -> None:
        """
        Add one or more new columns via a streaming temp-file swap:

        1. Open original file for reading.
        2. Write updated header line to a .tmp file.
        3. Stream remaining content in _COPY_CHUNK-byte chunks.
        4. Atomically rename .tmp over original.

        Raises SchemaLockedError if schema is locked and any header is new.
        Never loads the full file into RAM.
        """
        it = (header,) if isinstance(header, str) else header

        # Collect only genuinely new headers; respect schema lock
        new_buf = []
        for h in it:
            if not h:
                continue
            if self._is_header(h):
                continue
            if self._schema_locked:
                raise SchemaLockedError(
                    f"Schema is locked. Cannot add new column: '{h}'"
                )
            new_buf.append(h)

        if not new_buf:
            return

        try:
            src = open(self.file_name)
        except OSError:
            return

        tmp_path = self.file_name + ".tmp"
        try:
            dst = open(tmp_path, "w")
        except OSError:
            src.close()
            return

        try:
            orig_first = src.readline()
            if not orig_first:
                # Empty file: write all headers in one shot
                existing = self._header_buffer.to_tuple()
                all_headers = (
                    (existing + tuple(new_buf)) if existing else tuple(new_buf)
                )
                dst.write(",".join(all_headers) + "\n")
            else:
                orig_first = orig_first.rstrip("\r\n")
                # Ensure buffer is populated even if init() skipped _get_headers
                if self._header_buffer.is_empty():
                    self._set_headers(tuple(self._split_line(orig_first)))
                existing = self._header_buffer.to_tuple()
                new_hdr_line = (
                    ",".join(existing + tuple(new_buf))
                    if existing
                    else ",".join(new_buf)
                )
                dst.write(new_hdr_line + "\n")
                # Stream remainder in small chunks to stay RAM-friendly
                while True:
                    chunk = src.read(_COPY_CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
        finally:
            src.close()
            dst.close()

        # Atomic replace (handle platform differences gracefully)
        try:
            os.remove(self.file_name)
        except OSError:
            pass
        try:
            os.rename(tmp_path, self.file_name)
        except OSError:
            try:
                os.replace(tmp_path, self.file_name)
            except Exception:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                raise

        # Commit new headers to the in-memory buffer
        for h in new_buf:
            self._add_header(h)

    # ------------------------------------------------------------------ #
    # Write API                                                            #
    # ------------------------------------------------------------------ #

    def write(self, key: str, value) -> None:
        """
        Append a **sparse** row: only the ``key`` column is set; every other
        column is written as an empty field.

        Best for logging a single measurement at a time without building a
        full dict.  If ``key`` is a new column it is added to the header
        (unless the schema is locked).

        Example::

            csv.write("temperature", 23.5)
            # -> row: ,23.5,,  (if headers are ts,temperature,humidity,...)
        """
        self.init()
        if not self._is_header(key):
            self._write_header(key)

        try:
            f = open(self.file_name, "a")
        except OSError:
            return

        try:
            headers = self._header_buffer.to_tuple()
            first = True
            for h in headers:
                if not first:
                    f.write(",")
                first = False
                if h == key:
                    f.write(self._escape_field(value))
                # other columns: intentionally empty — no write needed
            f.write("\n")
        finally:
            f.close()

    def write_row(self, row: dict[str]) -> None:
        """
        Append a **full** row from a ``dict``.  Keys not in ``row`` produce
        empty fields; keys not yet in the header are added automatically
        (unless the schema is locked).

        Example::

            csv.write_row({"ts": uptime(), "temp": 23.5, "humidity": 60})
        """
        self.init()

        new_headers = [k for k in row if not self._is_header(k)]
        if new_headers:
            self._write_header(new_headers)

        try:
            f = open(self.file_name, "a")
        except OSError:
            return

        try:
            headers = self._header_buffer.to_tuple()
            first = True
            for h in headers:
                if not first:
                    f.write(",")
                first = False
                v = row.get(h)
                if v is not None:
                    f.write(self._escape_field(v))
            f.write("\n")
        finally:
            f.close()

    # ------------------------------------------------------------------ #
    # Read API                                                             #
    # ------------------------------------------------------------------ #

    def iter_rows(self, cast: bool = False):
        """
        Stream every data row as a ``dict`` mapping header name -> value.

        Parsing is RFC 4180-compliant via ``_split_line``, so quoted fields
        containing commas are handled correctly.  Only one line is held in
        RAM at a time.

        Args:
            cast: When True, numeric strings are auto-converted to int or
                  float.  Strings that aren't numbers are left as-is.

        Example::

            for row in csv.iter_rows(cast=True):
                process(row["temp"])    # arrives as float
        """
        self.init()
        headers = self._get_headers()
        if not headers:
            return

        try:
            f = open(self.file_name)
        except OSError:
            return

        try:
            f.readline()  # discard header line
            for raw in f:
                raw = raw.rstrip("\r\n")
                if not raw:
                    continue  # skip blank lines
                parts = self._split_line(raw)
                row = {}
                for idx, h in enumerate(headers):
                    v = parts[idx] if idx < len(parts) else ""
                    row[h] = self._cast(v) if cast else v
                yield row
        finally:
            f.close()

    def find_rows(self, key: str, value, cast: bool = False):
        """
        Stream only the rows where ``row[key] == value``.

        Filtering happens on the raw string value unless ``cast=True``, in
        which case the ``value`` argument is also cast before comparison.
        No additional RAM beyond a single row dict.

        Args:
            key:   Column name to match on.
            value: Value to match (compared as string by default).
            cast:  Apply auto-cast to all values in matched rows (and to
                   ``value`` itself for a consistent comparison).

        Example::

            for row in csv.find_rows("sensor_id", "A1"):
                print(row["temp"])

            # With numeric match:
            for row in csv.find_rows("temp", 23, cast=True):
                print(row)
        """
        needle = self._cast(str(value)) if cast else str(value)
        for row in self.iter_rows(cast=cast):
            if row.get(key) == needle:
                yield row

    def get_last_n_rows(self, n: int, cast: bool = False) -> list[dict]:
        """
        Return the **last** ``n`` data rows as an ordered list.

        Streams the entire file but keeps only a rolling window of ``n``
        row dicts in RAM using a fixed-size circular buffer — so memory
        usage is O(n), not O(file size).  Useful for displaying the most
        recent sensor readings.

        Args:
            n:    Number of tail rows to return (0 returns []).
            cast: Auto-cast numeric values if True.

        Returns:
            List of row dicts in chronological order (oldest first).

        Example::

            recent = csv.get_last_n_rows(10, cast=True)
            avg_temp = sum(r["temp"] for r in recent) / len(recent)
        """
        if n <= 0:
            return []

        # Circular buffer — pre-allocate n slots, no realloc on roll
        buf = [None] * n
        head = 0
        count = 0

        for row in self.iter_rows(cast=cast):
            buf[head] = row
            head = (head + 1) % n
            count += 1

        if count == 0:
            return []

        actual = min(count, n)
        start = (head - actual) % n
        return [buf[(start + i) % n] for i in range(actual)]

    def count_rows(self) -> int:
        """
        Return the number of data rows (header line excluded).

        Streams the file counting non-blank lines — no row data is parsed
        or stored.  Suitable for checking dataset size before deciding
        whether to rotate the file.

        Example::

            if csv.count_rows() > 1000:
                csv.clear()
        """
        self.init()
        try:
            f = open(self.file_name)
        except OSError:
            return 0

        try:
            f.readline()  # skip header
            total = 0
            for line in f:
                if line.strip():
                    total += 1
            return total
        finally:
            f.close()

    # ------------------------------------------------------------------ #
    # Utilities                                                            #
    # ------------------------------------------------------------------ #

    def clear(self) -> None:
        """
        Truncate the file to zero bytes and reset all in-memory state.
        The schema lock is **preserved** — call ``schema_unlock()`` first
        if you intend to rebuild with a different schema.
        """
        try:
            f = open(self.file_name, "w")
            f.truncate(0)
            f.close()
        except OSError:
            pass
        self._header_buffer = RingBuffer(self._max_keys)
        self._inited = False

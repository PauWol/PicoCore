"""
PicoCore V2 Config Module

This module provides a Config class for reading and writing configuration files.

The config file is expected to be in INI format with the following structure:

[Class]
key = value

[Class.Sub]
key = value
sub = {key: value}

Usage (If not initialized):
    from core.config import get_config

    config = get_config("config.ini")
    value = config.get("Class.Sub.key")
    config.set("Class.Sub.key", "new_value")

Usage (If already initialized):
    from core.config import get_config

    config = get_config().get("Class.Sub.key")
    config.set("Class.Sub.key", "new_value")
"""


class Config:
    __slots__ = ("path", "data", "_cls", "_sub")

    def __init__(self, path):
        self.path = path
        self.data = {}
        self._cls = None
        self._sub = None
        self._parse()

    # ---------------- PARSER ----------------

    def _parse(self):
        self.data = {}
        self._cls = None
        self._sub = None

        with open(self.path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line[0] == "#":
                    continue

                # section
                if line[0] == "[" and line[-1] == "]":
                    name = line[1:-1]
                    if "." in name:
                        cls, sub = name.split(".", 1)
                        self._cls = cls.strip()
                        self._sub = sub.strip()

                        if self._cls not in self.data:
                            self.data[self._cls] = {}
                        if self._sub not in self.data[self._cls]:
                            self.data[self._cls][self._sub] = {}
                    else:
                        self._cls = name.strip()
                        self._sub = None

                        if self._cls not in self.data:
                            self.data[self._cls] = {}

                    continue

                # property
                i = line.find("=")
                if i == -1 or self._cls is None:
                    continue

                key = line[:i].strip()
                val = self._convert(line[i + 1 :].strip())

                if self._sub:
                    self.data[self._cls][self._sub][key] = val
                else:
                    self.data[self._cls][key] = val

    # ---------------- VALUE CONVERSION ----------------

    def _convert(self, v):
        if not v:
            return ""

        # strip inline comment (only if not quoted)
        if "#" in v and v[0] not in ("'", '"'):
            v = v.split("#", 1)[0].strip()
            if not v:
                return ""

        # bool
        if v == "true":
            return True
        if v == "false":
            return False

        # remove numeric underscores (MicroPython safe)
        v_clean = v.replace("_", "")

        # int (fast path)
        if "." not in v_clean:
            try:
                return int(v_clean)
            except ValueError:
                pass

        try:
            return float(v_clean)
        except ValueError:
            pass

        # list
        if v[0] == "[" and v[-1] == "]":
            inner = v[1:-1]
            if not inner:
                return []
            return [self._convert(x.strip()) for x in inner.split(",") if x]

        # quoted string
        if (v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'"):
            return v[1:-1]

        return v

    # ---------------- SAVE ----------------

    def _to_str(self, v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, list):
            return "[" + ", ".join(self._to_str(x) for x in v) + "]"
        return '"' + str(v) + '"'

    def _save(self):
        with open(self.path, "w") as f:
            for cls, content in self.data.items():
                # top-level props
                wrote_header = False

                for k, v in content.items():
                    if not isinstance(v, dict):
                        if not wrote_header:
                            f.write(f"[{cls}]\n")
                            wrote_header = True
                        f.write(f"{k} = {self._to_str(v)}\n")

                if wrote_header:
                    f.write("\n")

                # subsections
                for k, v in content.items():
                    if isinstance(v, dict):
                        f.write(f"[{cls}.{k}]\n")
                        for sk, sv in v.items():
                            f.write(f"{sk} = {self._to_str(sv)}\n")
                        f.write("\n")

    # ---------------- API ----------------

    def get(self, key):
        if key == "*":
            return self.data

        d = self.data
        for part in key.split("."):
            if not isinstance(d, dict):
                return None
            d = d.get(part)
            if d is None:
                return None
        return d

    def set(self, key, value):
        parts = key.split(".")
        d = self.data

        for p in parts[:-1]:
            if p not in d or not isinstance(d[p], dict):
                d[p] = {}
            d = d[p]

        d[parts[-1]] = value
        self._save()


_config: Config | None = None


def get_config(path: str = None):
    global _config
    if not _config:
        _config = Config(path)

    return _config

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
    """
    Config class for reading and writing a configuration file.
    """
    __slots__ = ("path", "file_object", "current_class", "subclasses")

    def __init__(self, path: str) -> None:
        """
        Initialize the config.
        :param path: The path to the config file.
        """
        self.path = path
        self.file_object: dict[str, dict[str, object]] = {}
        # structure: { "Class": {key:val, "sub": { ... }}}
        self.current_class: tuple[str, str, bool] | tuple[None,None,bool] \
        = (None, None, False)  # (class, subclass, is_sub)
        self.subclasses: dict[str, set[str]] = {}  # record of subclasses per class -> set(...)
        self._parse()

    # ---------- small helpers ----------
    @staticmethod
    def _is_class(line: str) -> bool:
        return line.startswith("[") and line.endswith("]") and "." not in line

    @staticmethod
    def _is_subclass(line: str) -> bool:
        return line.startswith("[") and line.endswith("]") and "." in line

    @staticmethod
    def _get_class_subclass(line: str) -> tuple[str, str]:
        cls, sub = line[1:-1].split(".", 1)
        return cls.strip(), sub.strip()

    @staticmethod
    def _is_comment(line: str) -> bool:
        return line.startswith("#")

    @staticmethod
    def _is_property(line: str) -> bool:
        return "=" in line

    @staticmethod
    def _is_blank(line: str) -> bool:
        return not line

    def _parse_inline_dict(self, value: str) -> dict[str, object]:
        inner = value[1:-1].strip()
        out: dict[str, object] = {}
        if not inner:
            return out
        # split on commas (note: won't handle nested commas in strings)
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                key = k.strip().strip('"').strip("'")
                out[key] = self._convert_value(v.strip())
        return out

    def _convert_lists(self,v: str) -> list[object] | None:
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            if not inner:
                return []
            items = [item.strip() for item in inner.split(",")]
            return [self._convert_value(it) for it in items if it]
        return None

    def _convert_inline_inline_dicts(self,v: str) -> dict[str, object] | None:
        if v.startswith("{") and v.endswith("}"):
            try:
                return self._parse_inline_dict(v)
            except ValueError:
                pass
        return None

    @staticmethod
    def _convert_booleans(v: str) -> bool | None:
        lv = v.lower()
        if lv == "true":
            return True
        if lv == "false":
            return False
        return None

    @staticmethod
    def _convert_numeric_ints(v: str) -> int | None:
        try:
            if "." not in v:
                # integer
                return int(v, 0)  # allow 0x.. hex too
        except ValueError:
            pass
        return None

    @staticmethod
    def _convert_floats(v: str) -> float | None:
        try:
            return float(v)
        except ValueError:
            pass
        return None

    @staticmethod
    def _convert_strings(v: str) -> str | None:
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            return v[1:-1]
        return None

    def _convert_value(self, value: str) -> object:
        v = value.strip()
        if not v:
            return ""

        # remove inline comments after the value
        if "#" in v:
            # keep hashes inside quotes
            if not (v.startswith('"') or v.startswith("'")):
                v = v.split("#", 1)[0].strip()

        # lists
        result: object = self._convert_lists(v)

        # inline dicts
        if not result:
            result = self._convert_inline_inline_dicts(v)

        # booleans
        if not result:
            result = self._convert_booleans(v)

        # numeric ints (supports negative)
        if not result:
            result = self._convert_numeric_ints(v)

        # floats
        if not result:
            result = self._convert_floats(v)

        # strings - strip surrounding quotes if present
        if not result:
            result = self._convert_strings(v)

        return result

    def _value_to_string(self, value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            items: str | list[str] = ", ".join(self._value_to_string(i) for i in value)
            return f"[{items}]"
        if isinstance(value, dict):
            items = []
            for k, v in value.items():
                items.append(f"\"{k}\" = {self._value_to_string(v)}")
            return "{ " + ", ".join(items) + " }"
        # fallback string - quote always
        s = str(value)
        # escape existing quotes naively
        s = s.replace('"', '\\"')
        return f"\"{s}\""

    def _load(self) -> str:
        with open(self.path, "r", encoding="utf-8") as f:
            return f.read()


    def _parse(self) -> None:
        content = self._load()
        self.file_object = {}
        self.subclasses = {}
        self.current_class = (None, None, False)

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if self._is_blank(line) or self._is_comment(line):
                continue

            # section headers and properties expect trimmed lines
            if self._is_class(line):
                self._new_class(line)
            elif self._is_subclass(line):
                self._new_subclass(line)
            elif self._is_property(line):
                self._new_property(line)
            else:
                # unknown lines we retain as-is (or log)
                # print("[Warning] Unknown line:", raw_line)
                continue

    def _new_class(self, line: str) -> None:
        class_name = line[1:-1].strip()
        if class_name not in self.file_object:
            self.file_object[class_name] = {}
        if class_name not in self.subclasses:
            self.subclasses[class_name] = set()
        self.current_class = (class_name, None, False)

    def _new_subclass(self, line: str) -> None:
        cls, sub = self._get_class_subclass(line)
        if cls not in self.file_object:
            self.file_object[cls] = {}
        if cls not in self.subclasses:
            self.subclasses[cls] = set()
        self.subclasses[cls].add(sub)
        # ensure subclass dict exists
        if sub not in self.file_object[cls] or not isinstance(self.file_object[cls].get(sub), dict):
            self.file_object[cls].setdefault(sub, {})
        self.current_class = (cls, sub, True)

    def _new_property(self, line: str) -> None:
        if not self.current_class or self.current_class[0] is None:
            # unspecified class; ignore or create a default top-level?
            return
        key, val = line.split("=", 1)
        key = key.strip()
        value = self._convert_value(val.strip())
        cls, sub, is_sub = self.current_class
        if is_sub:
            # make sure subclass dict exists
            self.file_object.setdefault(cls, {})
            if not isinstance(self.file_object[cls].get(sub), dict):
                self.file_object[cls][sub] = {}
            # assign (overwrite existing)
            self.file_object[cls][sub][key] = value
        else:
            self.file_object.setdefault(cls, {})
            self.file_object[cls][key] = value

    def _save(self) -> None:
        # write in deterministic order for repeatability (sort keys)
        with open(self.path, "w", encoding="utf-8") as f:
            for class_name in sorted(self.file_object.keys()):
                data = self.file_object[class_name]
                # properties are keys not listed as subclasses
                props = {}
                subs = {}
                subnames = self.subclasses.get(class_name, set())
                for k in sorted(data.keys()):
                    if k in subnames and isinstance(data[k], dict):
                        subs[k] = data[k]
                    else:
                        props[k] = data[k]

                if props:
                    f.write(f"[{class_name}]\n")
                    for k in sorted(props.keys()):
                        f.write(f"{k} = {self._value_to_string(props[k])}\n")
                    f.write("\n")
                for sub_name in sorted(subs.keys()):
                    f.write(f"[{class_name}.{sub_name}]\n")
                    for k in sorted(subs[sub_name].keys()):
                        f.write(f"{k} = {self._value_to_string(subs[sub_name][k])}\n")
                    f.write("\n")

    def get(self, key: str) -> object | None:
        """
        Get a value from the config.
        :param key: String with dot notation to access the value (e.g. "class.subclass.key")
                    or "*" to get the whole config.
        :return:  The value or None if not found.
        """
        if key == "*":
            return self.file_object
        parts = key.split(".")
        d = self.file_object
        for p in parts:
            if not isinstance(d, dict):
                return None
            d = d.get(p)
            if d is None:
                return None
        return d

    def set(self, key: str, value: object) -> None:
        """
        Set a key; value pair in the config.
        :param key:  String with dot notation to access the value (e.g. "class.subclass.key").
        :param value: The value to set.
        :return: None
        """
        parts = key.split(".")
        d = self.file_object
        # create intermediate dicts if necessary
        for p in parts[:-1]:
            if p not in d or not isinstance(d[p], dict):
                d[p] = {}
            d = d[p]
        d[parts[-1]] = value
        # update subclass records if setting a whole dict on a subclass
        if len(parts) == 2:
            cls, sub = parts[0], parts[1]
            if isinstance(value, dict):
                self.subclasses.setdefault(cls, set()).add(sub)
        self._save()


_config_instance = None


def get_config(path: str | None = None) -> Config | ValueError:
    """
    Get the config instance.
    :param path: The path to the config file or None if already initialized.
    :return: The config instance or ValueError if not initialized.
    """
    global _config_instance  # pylint: disable=global-statement
    if _config_instance is None:
        if path is None:
            raise ValueError("Config not initialized; pass path on first get_config(path)")
        _config_instance = Config(path)
    return _config_instance


def reset_config() -> None:
    """
    Reset the config instance to None.
    This is not recommended for normal use.
    """
    global _config_instance  # pylint: disable=global-statement
    _config_instance = None

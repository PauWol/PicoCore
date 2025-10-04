from sys import modules

class Config:
    def __init__(self, path: str):
        self.path = path
        self.file_object: dict = {}
        self.current_class: tuple = ()
        self.subclasses = {}
        self._parse()

    @staticmethod
    def _isClass(line: str):
        return line.startswith("[") and line.endswith("]") and "." not in line

    @staticmethod
    def _isSubClass(line: str):
        return line.startswith("[") and line.endswith("]") and "." in line

    @staticmethod
    def _getClassSubClass(line: str):
        return line[1:-1].split(".")

    @staticmethod
    def _isComment(line: str):
        return line.startswith("#")

    @staticmethod
    def _isProperty(line: str):
        return "=" in line

    @staticmethod
    def _isBlank(line: str):
        return not line.strip()

    def _parse_inline_dict(self, value: str):
        """
        Custom parser for inline dictionaries in the format:
        { "a" = 1, "b" = 2 }
        """
        inner = value[1:-1].strip()  # Remove surrounding { and }
        result = {}
        if inner:
            parts = inner.split(",")
            for part in parts:
                if "=" in part:
                    k, v = part.split("=", 1)
                    k = k.strip().strip('"').strip("'")
                    v = v.strip()
                    result[k] = self._convert_value(v)
        return result

    def _convert_value(self, value: str):
        """Convert string values to appropriate types (int, float, bool, list, dict)."""
        value = value.strip()
        # Handle booleans
        if value.lower() in ["true", "false"]:
            return value.lower() == "true"
        # Handle integers
        if value.isdigit():
            return int(value)
        # Handle floats
        try:
            return float(value)
        except ValueError:
            pass
        # Handle lists
        if value.startswith("[") and value.endswith("]"):
            items = value[1:-1].split(",")
            return [self._convert_value(item.strip()) for item in items if item.strip()]
        # Handle dictionaries using our custom parser
        if value.startswith("{") and value.endswith("}"):
            try:
                return self._parse_inline_dict(value)
            except Exception:
                pass
        # Default: return as string without extra quotes
        return value.strip('"')

    def _value_to_string(self, value):
        """Convert a Python value back to a string representation for file saving."""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, list):
            items = ", ".join(self._value_to_string(item) for item in value)
            return f"[{items}]"
        elif isinstance(value, dict):
            # Build inline table without wrapping quotes
            items = []
            for k, v in value.items():
                items.append(f"\"{k}\" = {self._value_to_string(v)}")
            inline = "{ " + ", ".join(items) + " }"
            return inline
        else:
            return f"\"{value}\""

    def _classExists(self, key: str):
        return key in self.file_object

    def _load(self):
        try:
            with open(self.path) as f:
                return f.read()
        except OSError as e:
            print(f"[Error] Config file not found: {self.path}")
            raise Exception(e)

    def _parse(self):
        for line in self._load().splitlines():
            if self._isComment(line) or self._isBlank(line):
                continue

            if self._isClass(line):
                self._newClass(line)
            elif self._isSubClass(line):
                self._newSubClass(line)
            elif self._isProperty(line):
                self._newProperty(line)
            else:
                print(f"[Warning] Unknown line: {line}")

    def _newClass(self, line: str):
        class_name = line[1:-1]
        if not self._classExists(class_name):
            self.current_class = (class_name, None, False)
            self.file_object.setdefault(class_name, {})
            self.subclasses[class_name] = set()

    def _newSubClass(self, line: str):
        cls, subclass = self._getClassSubClass(line)
        self.current_class = (cls, subclass, True)
        if not self._classExists(cls):
            self.file_object.setdefault(cls, {})
            self.subclasses[cls] = set()
        self.subclasses[cls].add(subclass)
        self.file_object[cls].setdefault(subclass, {})

    def _newProperty(self, line: str):
        if not self.current_class or self.current_class[0] is None:
            print(f"[Warning] No current class to add property to: {line}")
            return
        key, value = line.split("=", 1)
        key = key.strip()
        value = self._convert_value(value.strip())
        if self.current_class[2]:
            cls, subclass, _ = self.current_class
            self.file_object[cls][subclass].setdefault(key, value)
        else:
            self.file_object[self.current_class[0]].setdefault(key, value)

    def _save(self):
        """
        Save the current configuration back to the file in a TOML-like format.
        """
        with open(self.path, "w") as f:
            for class_name, data in self.file_object.items():
                # Separate properties from sub-tables using the recorded subclass names.
                props = {}
                subs = {}
                for key, value in data.items():
                    if key in self.subclasses.get(class_name, set()):
                        subs[key] = value
                    else:
                        props[key] = value

                # Write the main class and its properties (if any)
                if props:
                    f.write(f"[{class_name}]\n")
                    for key, value in props.items():
                        f.write(f"{key} = {self._value_to_string(value)}\n")
                    f.write("\n")
                # Write each subclass and its properties
                for sub_name, sub_data in subs.items():
                    f.write(f"[{class_name}.{sub_name}]\n")
                    for key, value in sub_data.items():
                        f.write(f"{key} = {self._value_to_string(value)}\n")
                    f.write("\n")

    def get(self, key: str):
        """
        Retrieve a configuration value using a dot-separated key.
        For example, get("unit.test.int") returns the int value.
        Use get("*") to get the whole config.
        """
        if key == "*":
            return self.file_object
        parts = key.split(".")
        d = self.file_object
        for part in parts:
            if d is None:
                return None
            d = d.get(part)
        return d

    def set(self, key: str, value):
        """
        Set a configuration value using a dot-separated key.
        Updates the in-memory config and saves the changes.
        """
        parts = key.split(".")
        d = self.file_object
        for part in parts[:-1]:
            if part not in d or not isinstance(d[part], dict):
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value
        self._save()

if not hasattr(modules[__name__], "logger_instance"):
    #print("[PicoOS] Config Singleton Created")
    config_instance: Config | None = None

def get_config():
    return config_instance

if __name__ == "__main__":
    config = Config("test.toml")
    print(config.get("*"))
    print("Before:", config.get("unit.test.dict"))
    config.set("test.test.dict", {"a": 7, "b": 0})
    print("After:", config.get("test.test.dict"))
    print(config.get("*"))



# To MPY

This tool compiles `.py` files into `.mpy` files for use with MicroPython.

## Requirements

- **mpy-cross** (the MicroPython cross-compiler)

## Installation

1. Determine which version of MicroPython your `.py` files target (e.g., `1.26.1`).
2. Visit the [mpy-cross PyPI page](https://pypi.org/project/mpy-cross/#history) and locate the release matching your MicroPython version.
3. Install the correct version with `pip`:

```bash
pip install mpy-cross==1.26.1.post2  # Example for MicroPython 1.26.1
```

## Usage

### Manual compilation

Using the `to-mpy.py` file, you can run the tool either from an IDE (by adapting the Python script) or directly from the command line:

```bash
python to-mpy.py <source_dir> <output_dir>
```

- `<source_dir>`: Directory containing your `.py` files.
- `<output_dir>`: Destination directory for the compiled `.mpy` files.

### Full manual method (using mpy-cross directly)

From the Python command line:

```bash
python -m mpy_cross <args>
python -m mpy_cross --help
```

From Python code:

```python
import mpy_cross

mpy_cross.run(*args, **kwargs)

import subprocess
proc = mpy_cross.run('--version', stdout=subprocess.PIPE)
```

For more documentation see the official PyPI page: [mpy-cross](https://pypi.org/project/mpy-cross/).

### Automated compilation (Windows only)

If you are using the provided project folder structure from GitHub, you can use the included `compile.bat` script. This script is essentially a wrapper around the manual `to-mpy.py` method, giving you a one‑click build process:

- Reads the `.version` files from `src/core` and `build/core`.
- Compares versions and warns if they differ or are missing.
- Optionally deletes and recreates the build directory before compiling.
- Invokes `to-mpy.py` with `src/core` as input and `build/core` as output.
- After a successful build, writes the version information (or a timestamp if none exists) into `build/.version`.

⚠️ Note: The batch script only works out‑of‑the‑box if you keep the default folder structure of the project.

### Automated compilation with PowerShell (Windows only)

Alternatively, you can use the provided **PowerShell script** `compile.ps1`. This script is the smartest automation method — it takes care of version checks, ensures compatibility, and does everything for you. However, it is also the hardest to modify. If you want something very simple and out‑of‑the‑box (especially including `mpy-cross` setup), the PowerShell or batch script is the best choice. If you want something easier to understand and adapt, the manual Python method is better.

- Automatically detects both your MicroPython version and the installed `mpy-cross` version.
- Compares them with the project’s `.version` file.
- Prompts you if versions mismatch, or if nothing changed.
- Compiles **all** `.py` files from `src/core` into `.mpy` files in `build/core` (no skipping).
- Copies all non-`.py` files from `src/core` to `build/core` as well.

Run it from PowerShell like this:

```powershell
./compile.ps1
```

---

✅ After compilation, your `.mpy` files are ready to be deployed to your MicroPython board.

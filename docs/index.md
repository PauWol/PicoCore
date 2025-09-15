# PicoCore — Documentation

> **PicoCore** — a lightweight, power-efficient MicroPython framework for Raspberry Pi Pico and Pico W.
>
> Designed for small autonomous robots, weather stations, and edge devices — simple to use, modular, and efficient.

---

## About & History

Before diving into PicoCore V2, it's useful to understand the project's history and why V2 exists. The original **PicoCore V1** is preserved as a **legacy release** due to major architectural flaws. Lessons learned from V1 inspired the design of V2, improving power efficiency, modularity, and maintainability.

[Read the full story →](about.md)

---

## What is PicoCore V2?

PicoCore V2 is a MicroPython-first runtime and set of libraries that:

- Focuses on **small size** and **low power** operation for Pico/Pico W devices.
- Exposes a **simple service API** for sensors, telemetry, and autonomous behaviors.
- Provides tools and scripts for building `.mpy` modules (compiled MicroPython) and for deploying documentation with MkDocs.
- Reuses good ideas from the V1 prototype but is a fresh, robust redesign.

---

## Quickstart (5 minutes)

### 1. Download PicoCore release

- Go to the [releases](https://github.com/PauWol/PicoCore/releases) page.
- Download the latest `.zip` or `.7z` archive.
- Inside the archive you will usually find:

  - a `README.md` or `instructions.txt`
  - precompiled `.mpy` libraries (the PicoCore API/runtime)
  - usually a matching MicroPython `.uf2` firmware file.

### 2. Flash MicroPython firmware

- Hold the **BOOTSEL** button on your Pico/Pico W and connect it to your PC via USB.
- It will mount as a **RPI-RP2** drive.
- If the release archive contains a `.uf2`, copy it directly to the device.
- If no `.uf2` is included, check the version hint in the README and download the correct MicroPython `.uf2` from [micropython.org](https://micropython.org/download/rp2-pico/).
- After copying, the device will reboot and unmount.

### 3. Copy PicoCore runtime

- Use Thonny or the provided helper script in the [scripts](https://github.com/PauWol/PicoCore/tree/main/scripts) folder to copy the PicoCore `.mpy` library folder to your Pico.
- Also copy any `config.toml`, `boot.py`, or `main.py` files included in the release.

### 4. Verify installation

- Open a REPL (e.g. Thonny) and import a PicoCore module to check it works.
- Once everything is on the device, you are ready to start programming with PicoCore.

[Continue: Using PicoCore →](setup.md)

---

## Build & Release (compiled `.mpy`)

- Compiled modules for MicroPython are stored per-release in `/releases/` (e.g. `releases/v2.0.0/core.mpy`).
- Release naming convention:

  - **Active**: `v2.x.y` (semantic versioning)
  - **Legacy**: `v1.x.y-legacy` (explicit legacy/deprecated tags)

**Build steps (example):**

```bash
# Use provided helper script (Windows)
scripts\compile.bat

# Example output
# build/core/*.mpy
# build/core/.version  <-- version written after successful build
```

---

## Versioning & Legacy Notes

> ⚠️ **Legacy — PicoCore V1**
> PicoCore V1 is preserved for historical and reference purposes only. It contained architectural issues that led to the V2 rewrite. Do **not** use it in new projects. See the releases page for `v1.*-legacy` archives and migration notes.

Recommended `.version` content (single-line):

```
2.0.0
```

---

## Architecture Overview

```mermaid
flowchart LR
  A[boot.py] --> B(core.init())
  B --> C[Service Manager]
  C --> D[Sensor Drivers]
  C --> E[Telemetry / Logging]
  C --> F[Network (Pico W)]
  C --> G[Application Services (Weather / Rover)]
```

- `boot.py` calls a small initialization method from `/core/`.
- `/core/` implements the service manager, drivers, and core APIs.
- Applications register services and are started by the service manager.

---

## Recommended Repo Layout

```
my-project/
├─ src/                # core source (MicroPython)
├─ build/              # auto-generated compiled outputs
├─ core/               # runtime API (core modules)
├─ docs/               # mkdocs sources (this site)
├─ scripts/            # build & deploy scripts (compile.bat)
├─ releases/           # packaged release assets (.zip/.tar or direct .mpy)
├─ venv/               # local virtualenv (gitignored)
├─ README.md
└─ requirements.txt
```

---

## Contributing & Development

- See [CONTRIBUTING](contributing.md) for code style, tests, and PR process.
- Use the `scripts/compile.bat` to produce `.mpy` artifacts.
- Keep your `.version` updated in `/core` (or `src`) when making incompatible changes.

---

## Troubleshooting (common items)

- **`mkdocs` not found** — activate venv and `pip install mkdocs mkdocs-material`.
- **Build scripts fail** — run from `cmd.exe` on Windows; script logs the resolved paths.
- **Pico not detected** — ensure device is mounted correctly and you have the correct firmware / MicroPython UF2.

---

## Contact & Links

- GitHub: [PauWol/PicoCore](https://github.com/PauWol/PicoCore)
- Issues & feature requests: Use the repository **Issues** page.
- License: See `LICENSE` in the repo root.

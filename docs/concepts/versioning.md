# Versioning

> This page deals with the version structure of PicoCore.

---

PicoCore uses a simple versioning system based on a `.version` file located in the `core` folder of the project. This file contains **two lines**:

1. **PicoCore version** – the version of the PicoCore framework.
2. **MicroPython version** – the version of MicroPython used.

Example of a `.version` file:

```{.version .no-copy title=".version" linenums="1"}
2.0.0
1.26.1
```

This `.version` file is important during **compilation and documentation generation**, as various processes rely on it.

!!! note "This page is mainly relevant for developers who want to build their own version of PicoCore or contribute to the project."

# About PicoCore

!!! abstract

        The story behind PicoCore: evolution, lessons learned,
        and the drive to make something that actually works.

---

## Legacy PicoCore V1

The original **PicoCore V1** was an experimental MicroPython framework for Raspberry Pi Pico devices. It aimed to simplify building small autonomous projects like weather stations and basic robots.

**Key points about V1:**

- **Legacy Only:** The V1 codebase is preserved only as a **legacy release**. It is no longer maintained due to major design flaws.
- **Limited Use:** While some concepts and code were useful, the architecture failed to deliver low power consumption in practice.
- **Practical Testing:** I once built a quick prototype weather station using scrap parts and a DHT11 sensor. Despite my calculations predicting at least 2 days of battery life, it barely lasted ~5 hours. Apparently, that tiny blinking indicator LED I mounted outside was a battery vampire.
- **Lessons Learned:** V1 highlighted poor service management, inefficient sensor polling, and general inefficiency. Coding felt awkward and more complicated than standard MicroPython, and my so-called PicoOS turned out to be more of a misnomer.

You can find V1 in the [releases](https://github.com/PauWol/PicoCore/releases/tag/v1.0.0-legacy) as a reference, but **do not use it for new projects**.

---

## My Story & Motivation for PicoCore V2

After V1, I had a grand vision: build an actual OS for a small robot I was designing. Many side projects pulled me away, and I realized quickly that PicoOS wasn’t really an OS. Embedding and recompiling the MicroPython firmware was a nightmare — hello CMake, Windows, WSL, and compiler headaches.

So, I pivoted: I switched to `.mpy`-converted library-like files, making the “OS” more of a runtime API. The name stuck, even if it was misleading.

One weekend — fueled by coffee and little sleep — I rewrote the whole PicoCore “OS” from scratch. By the end, tests on my lab setup (my dorm PC) were working perfectly. I grabbed a bunch of scrap materials and spent the rest of the weekend building a makeshift weather station:

- **Hardware:** Protein box enclosure, homemade PCB, improvised power supply from 4 Amazon batteries wired in series/parallel (~3.3–3.7 V, ~4 Ah).
- **Design:** DHT11 sensor in a modified pillbox with ventilation holes, cable routed into the body, indicator LED to blink every minute for 3 seconds.
- **Goal:** Measure temperature and humidity every 5 minutes overnight.

The next morning? Disaster. Only 5 data points logged. The timestamps were all over the place. The LED had apparently murdered my battery. V1’s approach wasn’t cutting it.

I realized it was time for a **smarter, developer-friendly system**:

- Precompiled PicoCore API/runtime with **auto features**: deep sleep, light sleep, CPU frequency adjustments, battery voltage monitoring, and more.
- Simple, intuitive code structure that actually works.
- A system that lets you focus on your project, not wrestling with the framework.

V2 was born from trial, error, and caffeine-fueled determination. The goal? Make something **usable, maintainable, and enjoyable** — and, hopefully, well-documented so future evolutions are easier to manage.

---

## PicoCore V2

**PicoCore V2** addresses the shortcomings of V1:

- **Redesigned Architecture:** Modular service manager, improved sensor and power management, and a robust runtime API.
- **Best Practices:** Follows modern MicroPython and embedded system conventions.
- **Low Power:** Optimized to maximize battery life in real-world autonomous devices.
- **Extensible:** Easier to add sensors, robots, or IoT applications.

V2 builds on the lessons learned from V1 but is **robust, maintainable, and production-ready**.

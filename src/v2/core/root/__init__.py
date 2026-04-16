"""
PicoCore V2 Root Module
"""

from .Root import root, task, start, stop, add_task
from .bus import emit, on, off, manual, bus
from .power import Power
# __all__ = ['Root', 'Power']

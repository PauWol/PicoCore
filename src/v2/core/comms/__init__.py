"""
PicoCore V2 Comms Module

This module provides functions for mesh communication (ESP-Only).
Wi-Fi and Bluetooth planned for future releases.
"""
from . import crc8
from ..queue import RingBuffer
from ..logging import logger
from ..config import get_config
from ..constants import MESH_SECRET
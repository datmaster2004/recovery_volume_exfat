# -*- coding: utf-8 -*-
from .constants import MAGIC, VERSION, BOOT_SIZE, ENTRY_SIZE
from .boot import Boot
from .volume import Volume
from exfat import recovery

MAGIC = b"XFATSIM\x00"
VERSION = 1
BOOT_SIZE = 512
ENTRY_SIZE = 256
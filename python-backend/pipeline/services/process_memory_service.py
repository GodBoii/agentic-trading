from __future__ import annotations

import ctypes
import gc
import sys


def release_unused_process_memory() -> bool:
    """Collect unreachable objects and return free libc arenas when supported."""

    gc.collect()
    if not sys.platform.startswith("linux"):
        return False
    try:
        libc = ctypes.CDLL(None)
        malloc_trim = libc.malloc_trim
        malloc_trim.argtypes = [ctypes.c_size_t]
        malloc_trim.restype = ctypes.c_int
        return bool(malloc_trim(0))
    except (AttributeError, OSError):
        return False

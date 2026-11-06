"""Keep the overlay in front of the game: tell Windows again and again that the window is a topmost one.

A game that takes the focus (or switches its own window mode) can push other topmost windows behind it. Putting the overlay
back on top is cheap, and it never takes the focus from the game.
"""

import ctypes
import sys
from ctypes import wintypes

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
REASSERT_MS = 500  # how often the overlay is put back on top


def reassert_topmost(hwnd: int) -> bool:
    """Put the window back on top of the other topmost windows without moving, resizing or activating it. False when this is not Windows or the call failed."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        set_window_pos = ctypes.windll.user32.SetWindowPos
        set_window_pos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        set_window_pos.restype = wintypes.BOOL
        return bool(set_window_pos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER))
    except Exception:
        return False

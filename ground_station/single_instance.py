"""Stop a second copy of the app from starting.

Two copies would each open their own kRPC connection and their own pill and bar, and an older copy
can sit on screen showing a countdown that never moves.
"""

from pathlib import Path

from PySide6.QtCore import QDir, QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from .branding import APP_NAME, LOCK_NAME


def acquire(path: Path | None = None) -> QLockFile | None:
    """The held lock, or None if another copy of the app is already running. Keep the result alive."""
    lock = QLockFile(str(path) if path else QDir.temp().filePath(LOCK_NAME))
    return lock if lock.tryLock(0) else None


def acquire_or_explain() -> QLockFile | None:
    """Like `acquire`, but tells the operator in a dialog when another copy is running."""
    lock = acquire()
    if lock is None:
        app = QApplication.instance() or QApplication([])
        QMessageBox.warning(
            None,
            APP_NAME,
            f"{APP_NAME} is already running.\n\n"
            "Close the other copy first (look for its pill, bar or control panel window).",
        )
    return lock

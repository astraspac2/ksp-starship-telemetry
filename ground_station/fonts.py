"""Register the bundled fonts: D-DIN (Datto) and Oxanium (The Oxanium Project Authors), both SIL OFL 1.1; licences in fonts/."""

from pathlib import Path

from PySide6.QtGui import QFontDatabase

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"


def load_bundled_fonts() -> list[str]:
    """Register every .ttf in fonts/ and return the family names Qt now knows. Call after QApplication exists."""
    families: list[str] = []
    for path in sorted(FONT_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id >= 0:
            families.extend(QFontDatabase.applicationFontFamilies(font_id))
    return sorted(set(families))

"""Scale the HUD to the monitor's resolution. Qt-free.

The bar is drawn in a 1920-wide frame, so on a 1920 x 1080 monitor it spans the screen. On a bigger or smaller screen the same
frame would be too small or too big; scaling it by the screen's width over 1920 keeps it spanning the same share of the screen.
The HUD scale setting still applies on top of that, as a fine adjustment.
"""

DESIGN_WIDTH = 1920
AUTO = "auto"
RESOLUTIONS = ("1280x720", "1366x768", "1600x900", "1920x1080", "2560x1440", "3440x1440", "3840x2160")
CHOICES = (AUTO,) + RESOLUTIONS


def label(choice: str) -> str:
    return "Automatic (this screen)" if choice == AUTO else choice.replace("x", " x ")


def resolution_scale(choice: str, screen_width: int) -> float:
    """What the HUD is multiplied by for this choice: the screen's own width when automatic, else the chosen resolution's."""
    if choice == AUTO:
        width = screen_width
    else:
        try:
            width = int(choice.split("x")[0])
        except (ValueError, IndexError):
            width = DESIGN_WIDTH
    return width / DESIGN_WIDTH if width > 0 else 1.0

"""Follow the ship's four flaps in the game, so the dial's ship can fold and swing them the same way. Qt-free.

The Starship Expansion Project flaps carry a `ModuleSEPControlSurface` with these fields (recorded with run_flap_probe.py):
Deploy (True once deployed), Deploy Angle and Authority Limiter (both degrees), and Pitch, Yaw and Roll (whether the flap
answers that axis). The game does not report the angle a flap is at this moment, so it is worked out: a deployed flap sits at
its Deploy Angle, plus the stick input times the authority limiter on the axes it answers. Nothing here sends anything to the game.

Folds are in degrees, in the order of FLAPS: how far a flap is folded in toward the heat shield from its fully deployed
(belly-flop) pose. 0 is the pose the model is drawn in.
"""

MODULE_NAME = "ModuleSEPControlSurface"
# (part name, forward?, left?): the model's "left" side is the one drawn as mirror +1
FLAPS = (
    ("SEP.26.SHIP.FWD.LEFT.FLAP", True, True),
    ("SEP.26.SHIP.FWD.RIGHT.FLAP", True, False),
    ("SEP.26.SHIP.AFT.LEFT.FLAP", False, True),
    ("SEP.26.SHIP.AFT.RIGHT.FLAP", False, False),
)
FLAP_COUNT = len(FLAPS)
READ_EVERY_SECONDS = 0.2
RESCAN_EVERY_SECONDS = 3.0  # looking for the flaps again when they were not found or stopped answering
FOLD_LIMITS = (-30.0, 90.0)
# which way the stick moves a flap (+1 = toward deployed): pitch works the forward and aft flaps against each other, roll the left and right
PITCH_SIGN_FORWARD = 1.0
ROLL_SIGN_LEFT = 1.0


def _number(text, default: float) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _flag(text) -> bool:
    return str(text).strip().lower() in ("true", "active", "yes", "1")


def fold_degrees(fields: dict, forward: bool, left: bool, pitch: float, yaw: float, roll: float) -> float:
    """How far in from fully deployed one flap is, from its module's fields and the stick input (-1..1 each)."""
    deploy_angle = _number(fields.get("Deploy Angle"), 0.0)
    limiter = _number(fields.get("Authority Limiter"), 0.0)
    deployed = _flag(fields.get("Deploy"))
    stick = 0.0
    if _flag(fields.get("Pitch")):
        stick += pitch * PITCH_SIGN_FORWARD * (1.0 if forward else -1.0)
    if _flag(fields.get("Roll")):
        stick += roll * ROLL_SIGN_LEFT * (1.0 if left else -1.0)
    stick = max(-1.0, min(1.0, stick))  # yaw is not drawn: how the ship's flaps answer it is not known
    current = (deploy_angle if deployed else 0.0) + limiter * stick
    return max(FOLD_LIMITS[0], min(FOLD_LIMITS[1], deploy_angle - current))


class FlapTracker:
    """Finds the flown vessel's four flaps and reads how far each is folded, a few times a second."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._vessel = None
        self._modules: list | None = None
        self._scan_at: float | None = None
        self._read_at: float | None = None
        self._folds: tuple[float, ...] | None = None

    def update(self, now: float, conn) -> tuple[float, ...] | None:
        """The four folds in FLAP_ORDER, or None when the flown vessel does not have the four flaps (or the game will not say)."""
        if self._read_at is not None and now - self._read_at < READ_EVERY_SECONDS:
            return self._folds
        self._read_at = now
        try:
            if self._modules is None:
                if self._scan_at is not None and now - self._scan_at < RESCAN_EVERY_SECONDS:
                    return self._folds
                self._scan_at = now
                self._scan(conn)
            if self._modules is None:
                self._folds = None
                return None
            control = self._vessel.control
            pitch, yaw, roll = control.pitch, control.yaw, control.roll
            self._folds = tuple(
                fold_degrees(dict(module.fields), forward, left, pitch, yaw, roll)
                for module, (_, forward, left) in zip(self._modules, FLAPS)
            )
        except Exception:  # the vessel changed or the game is busy: look again shortly
            self._modules, self._folds = None, None
        return self._folds

    def _scan(self, conn) -> None:
        vessel = conn.space_center.active_vessel
        modules = []
        for name, _, _ in FLAPS:
            parts = vessel.parts.with_name(name)
            if not parts:
                return
            module = next((m for m in parts[0].modules if m.name == MODULE_NAME), None)
            if module is None:
                return
            modules.append(module)
        self._vessel, self._modules = vessel, modules

"""Follow the ship's four flaps in the game, so the dial's ship can fold and swing them the same way. Qt-free.

The Starship Expansion Project flaps carry a `ModuleSEPControlSurface` with these fields (recorded with run_flap_probe.py):
Deploy, Deploy Angle and Authority Limiter (both degrees), and Pitch, Yaw and Roll (False while the flap answers that axis, as with Deploy). Deploy
reads True while the flaps are RETRACTED (tucked toward the steel side, a little ahead of lift-off) and False on the pad with the
flaps out, as pictured. The game does not report the angle a flap is at this moment, so it is worked out from those fields and the
stick input times the authority limiter on the axes the flap answers. Nothing here sends anything to the game.

Folds are in degrees, in the order of FLAPS: how far a flap is swung round the hull, away from the heat shield, from the pose the
model is drawn in, which is the flaps straight out sideways (fold 0). A retracted flap is folded by the deploy angle.
"""

import csv
from pathlib import Path

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
FOLD_LIMITS = (-90.0, 90.0)
# which way the stick moves a flap (+1 = toward deployed): pitch works the forward and aft flaps against each other, roll the left and right
PITCH_SIGN_FORWARD = 1.0
ROLL_SIGN_LEFT = -1.0  # (turned round after a test in the game)
YAW_SIGN = 1.0  # yaw works the diagonal pairs against each other: forward-left with aft-right


def _number(text, default: float) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _flag(text) -> bool:
    return str(text).strip().lower() in ("true", "active", "yes", "1")


def fold_degrees(fields: dict, forward: bool, left: bool, pitch: float, yaw: float, roll: float) -> float:
    """How far one flap is swung from the pose the model is drawn in, from its module's fields and the stick input (-1..1 each)."""
    deploy_angle = _number(fields.get("Deploy Angle"), 0.0)
    limiter = _number(fields.get("Authority Limiter"), 0.0)
    retracted = _flag(fields.get("Deploy"))  # the field is True while the flaps are RETRACTED: on the pad, flaps out, it reads False
    stick = 0.0
    if not _flag(fields.get("Pitch")):  # like Deploy, these read False while the flap answers the axis (the part's panel says "Active")
        stick += pitch * PITCH_SIGN_FORWARD * (1.0 if forward else -1.0)
    if not _flag(fields.get("Roll")):
        stick += roll * ROLL_SIGN_LEFT * (1.0 if left else -1.0)
    if not _flag(fields.get("Yaw")):
        stick += yaw * YAW_SIGN * (1.0 if forward else -1.0) * (1.0 if left else -1.0)
    stick = max(-1.0, min(1.0, stick)) if retracted else 0.0  # the stick moves a flap only while Deploy is True (recorded: the real flaps follow it then, and sit still with Deploy False)
    fold = (deploy_angle if retracted else 0.0) - limiter * stick
    return max(FOLD_LIMITS[0], min(FOLD_LIMITS[1], fold))


LOG_FIELDS = ("Deploy", "Pitch", "Yaw", "Roll", "Deploy Angle", "Authority Limiter")
LOG_LIMIT = 4000  # rows: the record is for finding out what the game said, not for keeping


class FlapTracker:
    """Finds the flown vessel's four flaps and reads how far each is folded, a few times a second.

    With a `log_path` it also writes a row whenever a flap's fields, the stick input or the folds change, so what the game
    said can be looked at afterwards."""

    def __init__(self, log_path: Path | None = None):
        self._log_path = log_path
        self._logged = 0
        self._last_logged = None
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
            read = [dict(module.fields) for module in self._modules]
            self._folds = tuple(
                fold_degrees(fields, forward, left, pitch, yaw, roll) for fields, (_, forward, left) in zip(read, FLAPS)
            )
            self._log(now, read, (pitch, yaw, roll))
        except Exception as exc:  # the vessel changed or the game is busy: look again shortly
            self._modules, self._folds = None, None
            self._log(now, None, None, f"{type(exc).__name__}: {exc}")
        return self._folds

    def _log(self, now: float, read, inputs, error: str = "") -> None:
        """One row when anything about the flaps changed since the last row."""
        if self._log_path is None or self._logged >= LOG_LIMIT:
            return
        row = [round(now, 2), error]
        if inputs is not None:
            row += [round(x, 2) for x in inputs]
        for index in range(FLAP_COUNT):
            fields = {} if read is None else read[index]
            row += [fields.get(name, "") for name in LOG_FIELDS]
            row.append("" if self._folds is None else round(self._folds[index], 1))
        key = tuple(row[2:])
        if key == self._last_logged:
            return
        self._last_logged = key
        try:
            new_file = self._logged == 0
            with open(self._log_path, "w" if new_file else "a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                if new_file:
                    writer.writerow(
                        ["t", "error", "input_pitch", "input_yaw", "input_roll"]
                        + [f"{label}_{name}" for label in ("fwd_left", "fwd_right", "aft_left", "aft_right") for name in (*LOG_FIELDS, "fold")]
                    )
                writer.writerow(row)
            self._logged += 1
        except OSError:
            self._logged = LOG_LIMIT  # not writable: stop trying

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

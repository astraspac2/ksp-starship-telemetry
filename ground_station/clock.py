"""The countdown clock: time relative to liftoff, driven by game time and under operator control.

Qt-free so it can be unit-tested.
"""

from enum import Enum

from .krpc_source import LiveSample, ReaderStatus

COUNTDOWN_HOLD = -0.5  # shown as T-00:00:01 while the countdown has run out but KSP has not launched


class ClockState(Enum):
    IDLE = "IDLE"  # armed at T-minus, not counting
    RUNNING = "RUNNING"
    HELD = "HELD"
    ABORTED = "ABORTED"  # countdown scrubbed by the operator; display only, nothing is sent to KSP


def has_launched(sample: LiveSample | None) -> bool:
    """KSP starts mission elapsed time on the first staging, i.e. at ignition/clamp release."""
    return sample is not None and (sample.met > 0 or sample.situation.lower() not in ("pre_launch", "prelaunch"))


class CountdownClock:
    """Time relative to liftoff, driven only by KSP's game clock, never the wall clock.

    The operator arms it at T-minus, then starts, holds, resumes or resets it. While running
    it follows KSP's universal time (UT), so a lagging or paused game slows or stops the
    countdown instead of letting it run ahead of the game. Once KSP reports the vessel has
    launched it shows KSP's mission elapsed time. If the feed drops the clock freezes at the
    last value from the game rather than guessing.

    `hold_at_zero=False` lets a demo source run on through T-0 instead of waiting for a launch
    that KSP would report. The pad / static-fire view needs the same: KSP keeps mission time at 0 on the pad
    (recorded in the static fire: met=0, pre_launch, with all 33 engines burning), so the clock keeps counting
    on game time through T-0 into T+.
    """

    def __init__(self, countdown_seconds: float, hold_at_zero: bool = True, hold_in_warp: bool = False):
        self._seconds = countdown_seconds
        self.hold_at_zero = hold_at_zero  # may be switched while running: the hold only clamps what is shown, the count goes on
        self.hold_in_warp = hold_in_warp  # freeze the countdown while KSP time warp is active
        self._state = ClockState.IDLE
        self._liftoff_ut: float | None = None  # UT at which the countdown reaches T-0; None until the next sample
        self._last_t = -countdown_seconds

    @property
    def state(self) -> ClockState:
        return self._state

    @property
    def countdown_seconds(self) -> float:
        return self._seconds

    @property
    def last_t(self) -> float:
        return self._last_t

    def start(self) -> None:
        if self._state is ClockState.IDLE:
            self._state = ClockState.RUNNING
            self._liftoff_ut = None

    def hold(self) -> None:
        if self._state is ClockState.RUNNING:
            self._state = ClockState.HELD

    def resume(self) -> None:
        if self._state is ClockState.HELD:
            self._state = ClockState.RUNNING
            self._liftoff_ut = None  # re-anchored from the clock's current value at the next sample

    def abort(self) -> None:
        """Scrub the countdown. Only meaningful before liftoff; the clock freezes where it is."""
        if self._state in (ClockState.RUNNING, ClockState.HELD) and self._last_t < 0:
            self._state = ClockState.ABORTED

    def reset(self, countdown_seconds: float | None = None) -> None:
        if countdown_seconds is not None:
            self._seconds = countdown_seconds
        self._state = ClockState.IDLE
        self._liftoff_ut = None
        self._last_t = -self._seconds

    def advance(self, ut: float | None, launched: bool, met: float, warping: bool = False) -> float:
        """Current time relative to liftoff given the newest game time, or the last value if none."""
        if launched:
            self._last_t = met
            return met
        if self._state is not ClockState.RUNNING or ut is None:
            return self._last_t
        if warping and self.hold_in_warp:
            self._liftoff_ut = None  # re-anchored from the held value once the warp ends
            return self._last_t
        if self._liftoff_ut is None:
            self._liftoff_ut = ut - self._last_t  # last_t is negative before liftoff
        t = ut - self._liftoff_ut
        self._last_t = min(t, COUNTDOWN_HOLD) if self.hold_at_zero else t
        return self._last_t

    def t(self, status: ReaderStatus) -> float:
        sample = status.sample
        if sample is None:
            return self._last_t
        return self.advance(sample.ut, has_launched(sample), sample.met, sample.warp_rate > 1.0)

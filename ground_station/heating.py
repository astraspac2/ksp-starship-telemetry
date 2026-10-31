"""How hot the ship's heat shield should look on re-entry. Qt-free.

The game's own heating is not read: the glow follows how hard the air is working on the ship, which is the dynamic pressure times
the speed (the heating rate of a body in the air is proportional to the air's density times its speed cubed, and that is twice
this). It is only for a vessel coming down, so the climb's max-Q does not light the shield.
"""

DESCENT_FROM = 30.0  # m/s of sinking before the shield may glow at all
GLOW_STARTS = 5.0e5  # Pa * m/s: below this the shield stays dark
GLOW_FULL = 2.0e7  # and by this it is white-hot
HEAT_RATE = 0.9  # per second: how fast the glow comes up when the heating rises
COOL_RATE = 0.7  # per second: how fast it cools again once the air thins out


def glow_target(dynamic_pressure_pa: float | None, speed_ms: float | None, vertical_speed_ms: float | None) -> float:
    """How strongly the shield glows right now, 0..1, from the air's pressure on the ship, its speed and whether it is sinking."""
    if dynamic_pressure_pa is None or speed_ms is None or vertical_speed_ms is None:
        return 0.0
    if not (dynamic_pressure_pa > 0 and speed_ms > 0) or vertical_speed_ms > -DESCENT_FROM:
        return 0.0
    heating = dynamic_pressure_pa * speed_ms
    x = min(max((heating - GLOW_STARTS) / (GLOW_FULL - GLOW_STARTS), 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def eased_glow(shown: float, target: float, seconds: float) -> float:
    """The glow on show, moved toward `target` over `seconds`: quick to heat up, slow to cool down."""
    reach = (HEAT_RATE if target > shown else COOL_RATE) * max(seconds, 0.0)
    return shown + max(-reach, min(reach, target - shown))

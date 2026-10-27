"""Which engines of a Starship Expansion Project (SEP) booster cluster are lit.

The SEP "Andrada" cluster is a single part holding all 33 engines in four groups that its
engine-mode switch shuts down or relights (modes "Outer Twenty", "Middle Eight", "Middle Two",
"Center Three"). kRPC only sees the first group directly, but the switch module's Thrust
field is the cluster's total. Every combination of groups gives a different engine count, so
total thrust divided by one engine's thrust tells exactly which groups are burning.

Qt- and kRPC-free so it can be unit-tested.
"""

from itertools import combinations

SWITCH_MODULE = "ModuleSEPEngineSwitch"
# Group name, engine count, and the dial positions they occupy: the dial lays out 33 engines as
# 3 centre (0-2), 10 middle (3-12, starting at 3 o'clock) and 20 outer (13-32). The two
# "Middle Two" engines are assumed to be the opposite pair at 3 and 9 o'clock; which two the
# mod actually uses has not been checked.
GROUPS = {
    "Center Three": (0, 1, 2),
    "Middle Two": (3, 8),
    "Middle Eight": (4, 5, 6, 7, 9, 10, 11, 12),
    "Outer Twenty": tuple(range(13, 33)),
}
CLUSTER_ENGINES = 33

# The cluster's engine-mode switch names the outermost ring that fires, and every ring inside it fires
# too: "Outer Twenty" is all 33, "Middle Eight" is 13, "Middle Two" is 5 and "Center Three" is 3.
# (Confirmed in a static fire: stepping through the modes gave 33, 13, 5, 3 engines lit.)
MODE_GROUPS = {
    "Outer Twenty": ("Center Three", "Middle Two", "Middle Eight", "Outer Twenty"),
    "Middle Eight": ("Center Three", "Middle Two", "Middle Eight"),
    "Middle Two": ("Center Three", "Middle Two"),
    "Center Three": ("Center Three",),
}
MIN_RUNNING_KN = 1.0  # below this the switch's own Thrust field says the cluster is not producing thrust
MIN_FUEL_FLOW = 5.0  # propellant units per second leaving the stage's tanks: the engines are burning

_COMBINATIONS = {
    sum(len(GROUPS[g]) for g in combo): combo
    for size in range(len(GROUPS) + 1)
    for combo in combinations(GROUPS, size)
}


def parse_thrust_kn(field: str) -> float:
    """The switch module's Thrust field, e.g. '18903.29', as kN. Unreadable -> 0."""
    cleaned = "".join(ch for ch in field if ch.isdigit() or ch in ".-")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def engines_burning(
    total_kn: float, first_group_thrust_n: float, first_group_engines: int, max_thrust_n: float, throttle: float
) -> float:
    """Estimated number of engines producing the cluster's total thrust.

    When the first group (the one kRPC reads) is burning, its own thrust per engine is the
    yardstick, which needs no throttle. Otherwise one engine's rated thrust at the current
    throttle is used.
    """
    if total_kn <= 0:
        return 0.0
    if first_group_thrust_n > 0 and first_group_engines > 0:
        per_engine = first_group_thrust_n / first_group_engines
    elif max_thrust_n > 0 and first_group_engines > 0 and throttle > 0.01:
        per_engine = max_thrust_n / first_group_engines * throttle
    else:
        return 0.0
    return total_kn * 1000.0 / per_engine


def lit_groups(engines: float) -> tuple[str, ...]:
    """The group combination whose engine count is closest to the estimate."""
    best = min(_COMBINATIONS, key=lambda count: abs(count - engines))
    return _COMBINATIONS[best]


def is_producing(switch_thrust_kn: float, first_module_thrust_n: float, fuel_flow: float) -> bool:
    """Whether the cluster is burning, from any of three independent signs.

    The switch's Thrust field is shown in the part window and stays at 0 while the window is closed, and
    kRPC's engine module may read nothing once the outer engines are off, so neither can be relied on
    alone. Propellant leaving the tanks says the engines are burning whatever the part window shows.
    """
    return switch_thrust_kn >= MIN_RUNNING_KN or first_module_thrust_n > 0 or fuel_flow >= MIN_FUEL_FLOW


def lit_for_mode(mode: str, producing: bool) -> tuple[bool, ...] | None:
    """Which dial positions are lit given the switch's mode name and whether the cluster is burning.

    None if the mode name is not one of the four known ones, so the caller can fall back to estimating
    from thrust.
    """
    groups = MODE_GROUPS.get(mode.strip())
    if groups is None:
        return None
    return lit_pattern(groups if producing else ())


def lit_pattern(groups: tuple[str, ...]) -> tuple[bool, ...]:
    """Per dial position (centre first), whether that engine is lit."""
    lit = [False] * CLUSTER_ENGINES
    for group in groups:
        for position in GROUPS[group]:
            lit[position] = True
    return tuple(lit)


def per_engine_rated_n(first_group_available_n: float, first_group_engines: int, remembered_n: float | None) -> float | None:
    """One cluster engine's thrust at full throttle, in newtons.

    Read from the first group (the one kRPC sees) while that group reports a rating; once the outer engines are
    switched off it reports nothing, so the last good value is kept. None if it has never been seen.
    """
    if first_group_available_n > 0 and first_group_engines > 0:
        return first_group_available_n / first_group_engines
    return remembered_n


def cluster_thrust_n(
    lit_engines: int,
    producing: bool,
    first_group_thrust_n: float,
    first_group_engines: int,
    switch_total_kn: float,
    rated_per_engine_n: float | None,
    throttle: float,
) -> float | None:
    """Total thrust of the cluster in newtons, or None when it is burning but cannot be worked out.

    In order of trust: the first group's own thrust per engine times the engines lit (it needs nothing else); the
    switch's Thrust field, the cluster total, which only updates while the part window is open; and last the engine's
    full-throttle rating times the throttle, an estimate.
    """
    if not producing or lit_engines <= 0:
        return 0.0
    if first_group_thrust_n > 0 and first_group_engines > 0:
        return lit_engines * first_group_thrust_n / first_group_engines
    if switch_total_kn >= MIN_RUNNING_KN:
        return switch_total_kn * 1000.0
    if rated_per_engine_n is not None and throttle > 0:
        return lit_engines * rated_per_engine_n * throttle
    return None

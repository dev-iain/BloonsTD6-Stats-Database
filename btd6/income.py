from __future__ import annotations

SUPER_CERAMIC_CASH = 87
ZEBRA_SUPER_CHILD = [("Black", 1)]


def surviving_children(
    name: str,
    children: dict[str, list[tuple[str, int]]],
    moab_names: frozenset[str] | set[str],
    super_ceramic: bool,
) -> list[tuple[str, int]]:
    released = children.get(name, [])
    if not super_ceramic or name in moab_names:
        return released
    if name == "Zebra":
        return ZEBRA_SUPER_CHILD
    return released[:1] and [(released[0][0], 1)]


def bloon_pop_cash(
    name: str,
    children: dict[str, list[tuple[str, int]]],
    moab_names: frozenset[str] | set[str],
    super_ceramic: bool,
) -> int:
    """Cash for fully popping one bloon: its own layer plus every released child."""
    own = SUPER_CERAMIC_CASH if super_ceramic and name == "Ceramic" else 1
    released = surviving_children(name, children, moab_names, super_ceramic)
    return own + sum(
        count * bloon_pop_cash(child, children, moab_names, super_ceramic)
        for child, count in released
    )

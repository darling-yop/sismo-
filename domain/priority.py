"""Populated-zone test and event-priority calculation."""


def is_populated(x, y, zones):
    """Return whether a point lies in or on any populated zone."""
    return any(zone.populated and zone.contains(x, y) for zone in zones)


def compute_priority(magnitude, depth, populated):
    """Return priority 3 (high), 2 (medium), or 1 (low)."""
    if magnitude >= 6.0 or (magnitude >= 4.5 and depth <= 30.0 and populated):
        return 3
    if magnitude >= 4.5:
        return 2
    return 1
"""Candidate and reference rules between seismic events."""

from datetime import timedelta


def is_candidate(a, b, w_hours, r_km):
    """Return whether event a can be the reference for event b."""
    if a.event_id == b.event_id:
        return False
    if not a.magnitude > b.magnitude:
        return False
    if not a.time < b.time:
        return False
    if b.time - a.time > timedelta(hours=w_hours):
        return False
    dx = round((a.x - b.x) * 10)
    dy = round((a.y - b.y) * 10)
    return dx * dx + dy * dy <= (r_km * 10) ** 2


def candidates(b, pool, w_hours, r_km):
    return [a for a in pool if is_candidate(a, b, w_hours, r_km)]


def choose_reference(candidate_list):
    """Choose by highest magnitude, latest time, then lowest identifier."""
    if not candidate_list:
        return None
    return min(candidate_list,
               key=lambda event: (-event.magnitude, -event.time.timestamp(), event.event_id))
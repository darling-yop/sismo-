"""Domain entities and input parsing/validation."""

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from core.tree_key import TreeKey

PENDING = "pendiente"
REVIEWED = "revisado"
ATTENTION_VALUES = (PENDING, REVIEWED)
ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class ValidationError(ValueError):
    """Invalid user data, with a Spanish message suitable for the GUI."""


def parse_id(value):
    """Accept an integer, numeric text, or SIS-prefixed identifier."""
    if isinstance(value, str):
        text = value.strip().upper()
        if text.startswith("SIS-"):
            text = text[4:]
        if not text.isdigit():
            raise ValidationError("el identificador debe ser un entero entre 1 y 999999")
        value = int(text)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 999999:
        raise ValidationError("el identificador debe ser un entero entre 1 y 999999")
    return value


def format_id(event_id):
    return f"SIS-{event_id:06d}"


def parse_decimal(value, label, low, high):
    """Parse a finite number in range with at most one decimal place."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label} debe ser un número")
    if not math.isfinite(number):
        raise ValidationError(f"{label} debe ser un número finito")
    if round(number, 1) != number:
        raise ValidationError(f"{label} admite máximo un decimal")
    if not low <= number <= high:
        raise ValidationError(f"{label} debe estar entre {low} y {high}")
    return number + 0.0


def parse_time(value):
    """Parse a datetime or ISO 8601 UTC text and return an aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0)
    try:
        return datetime.strptime(value, ISO_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        raise ValidationError("fecha inválida: use ISO 8601 UTC, ej. 2026-09-07T10:00:00Z")


def format_time(moment):
    return moment.strftime(ISO_FORMAT)


@dataclass(frozen=True)
class Zone:
    """Rectangle in the 0-1000 km plane; borders belong to the zone."""
    name: str
    x1: float
    y1: float
    x2: float
    y2: float
    populated: bool

    def contains(self, x, y):
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2


@dataclass
class Event:
    """Physical event data; the AVL node stores only its key."""
    event_id: int
    magnitude: float
    depth: float
    x: float
    y: float
    time: datetime
    revision: int = 1
    stations: set = field(default_factory=set)
    attention: str = PENDING
    populated: bool = False
    priority: int = 1
    reference_id: int | None = None

    @property
    def key(self):
        return TreeKey(self.priority, self.magnitude, self.event_id)

    def same_physical_data(self, magnitude, depth, x, y, time):
        return (self.magnitude == magnitude and self.depth == depth
                and self.x == x and self.y == y and self.time == time)

    def copy(self):
        return replace(self, stations=set(self.stations))
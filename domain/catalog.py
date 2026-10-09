"""Active event catalog backed by an AVL and indexed event dictionaries."""

from datetime import datetime, timedelta, timezone

from core.avl import AVL
from domain.associations import candidates, choose_reference, is_candidate
from domain.metrics import new_counters
from domain.models import (PENDING, REVIEWED, Event, ValidationError,
                           parse_decimal, parse_id, parse_time)
from domain.priority import compute_priority, is_populated

DEFAULT_CLOCK = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
FIELDS = ("magnitude", "depth", "x", "y", "time")


class Catalog:
    def __init__(self, zones=None, stations=None, clock=None):
        self.avl = AVL()
        self.zones = list(zones or [])
        self.stations = set(stations) if stations else None
        self.clock = clock or DEFAULT_CLOCK
        self.active = {}
        self.archived = {}
        self.deleted = {}
        self.W = 48
        self.R = 40
        self.L = 3
        self.T = 72
        self.counters = new_counters()

    def _validate(self, magnitude, depth, x, y, time):
        errors, out = [], {}
        rules = (("magnitude", "la magnitud", magnitude, -2.0, 10.0),
                 ("depth", "la profundidad", depth, 0.0, 700.0),
                 ("x", "la coordenada x", x, 0.0, 1000.0),
                 ("y", "la coordenada y", y, 0.0, 1000.0))
        for name, label, value, low, high in rules:
            try:
                out[name] = parse_decimal(value, label, low, high)
            except ValidationError as error:
                errors.append(str(error))
        try:
            moment = parse_time(time)
            if moment > self.clock:
                errors.append("la fecha no puede ser posterior al reloj de simulación")
            out["time"] = moment
        except ValidationError as error:
            errors.append(str(error))
        if errors:
            raise ValidationError("; ".join(errors))
        return out

    def _check_station(self, station):
        if not station or (self.stations is not None and station not in self.stations):
            raise ValidationError("estación desconocida")

    def validate_data(self, magnitude, depth, x, y, time):
        """Validate a report's physical data without modifying the catalog."""
        return self._validate(magnitude, depth, x, y, time)

    def check_station(self, station):
        self._check_station(station)

    def _derive(self, event):
        event.populated = is_populated(event.x, event.y, self.zones)
        event.priority = compute_priority(event.magnitude, event.depth, event.populated)

    def status_of(self, event_id):
        if event_id in self.active:
            return "activo"
        if event_id in self.archived:
            return "archivado"
        if event_id in self.deleted:
            return "eliminado"
        return None

    def create(self, event_id, magnitude, depth, x, y, time, station, revision=1):
        """Validate all input before mutating the catalog."""
        event_id = parse_id(event_id)
        status = self.status_of(event_id)
        if status:
            raise ValidationError(f"el identificador ya existe y está {status}")
        data = self._validate(magnitude, depth, x, y, time)
        self._check_station(station)
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValidationError("la revisión debe ser un entero positivo")

        event = Event(event_id, data["magnitude"], data["depth"], data["x"], data["y"],
                      data["time"], revision=revision, stations={station}, attention=PENDING)
        self._derive(event)
        self.avl.insert(event.key)
        self.active[event_id] = event
        self.refresh_associations(event_id)
        return event

    def correct(self, event_id, **changes):
        """Correct an active event and increment its revision."""
        event_id = parse_id(event_id)
        old = self.active.get(event_id)
        if old is None:
            raise ValidationError("solo se puede corregir un evento activo")
        unknown = set(changes) - set(FIELDS)
        if unknown:
            raise ValidationError(f"campos no corregibles: {sorted(unknown)}")
        merged = {name: getattr(old, name) for name in FIELDS}
        merged.update(changes)
        data = self._validate(**merged)

        new = old.copy()
        new.magnitude, new.depth = data["magnitude"], data["depth"]
        new.x, new.y, new.time = data["x"], data["y"], data["time"]
        new.revision = old.revision + 1
        new.attention = PENDING
        self._derive(new)

        if new.key != old.key:
            self.avl.delete(old.key)
            self.avl.insert(new.key)
        self.active[event_id] = new
        self.counters["corrections"] += 1
        self.refresh_associations(event_id)
        return new

    def revise(self, event_id, revision, station, magnitude, depth, x, y, time):
        """Apply a higher-revision report to an active or archived event."""
        event_id = parse_id(event_id)
        old = self.active.get(event_id)
        was_archived = old is None
        if was_archived:
            old = self.archived.get(event_id)
        if old is None:
            raise ValidationError("evento desconocido")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision <= old.revision:
            raise ValidationError("la revisión debe ser mayor que la vigente")
        self._check_station(station)
        data = self._validate(magnitude, depth, x, y, time)

        new = old.copy()
        new.magnitude, new.depth = data["magnitude"], data["depth"]
        new.x, new.y, new.time = data["x"], data["y"], data["time"]
        new.revision = revision
        new.stations.add(station)
        new.attention = PENDING
        self._derive(new)

        if was_archived:
            del self.archived[event_id]
            self.avl.insert(new.key)
        elif new.key != old.key:
            self.avl.delete(old.key)
            self.avl.insert(new.key)
        self.active[event_id] = new
        self.counters["corrections"] += 1
        self.refresh_associations(event_id)
        return new, was_archived

    def confirm(self, event_id, station):
        """Add a confirming station without modifying the AVL key."""
        event_id = parse_id(event_id)
        store = self.active if event_id in self.active else self.archived
        old = store.get(event_id)
        if old is None:
            raise ValidationError("evento desconocido")
        self._check_station(station)
        if station in old.stations:
            return False
        new = old.copy()
        new.stations.add(station)
        store[event_id] = new
        return True

    def mark_reviewed(self, event_id):
        """Mark an event reviewed without changing its tree key."""
        event_id = parse_id(event_id)
        old = self.active.get(event_id)
        if old is None:
            raise ValidationError("solo se puede revisar un evento activo")
        new = old.copy()
        new.attention = REVIEWED
        self.active[event_id] = new
        return new

    def delete(self, event_id):
        """Remove an event from the AVL while preserving its identity."""
        event_id = parse_id(event_id)
        event = self.active.get(event_id)
        if event is None:
            raise ValidationError("solo se puede eliminar un evento activo")
        self.avl.delete(event.key)
        del self.active[event_id]
        self.deleted[event_id] = event
        self.refresh_associations(event_id, removed=True)
        return event

    def lookup(self, event_id):
        """Return status and AVL-node metrics for an active event."""
        event_id = parse_id(event_id)
        status = self.status_of(event_id)
        event = (self.active.get(event_id) or self.archived.get(event_id)
                 or self.deleted.get(event_id))
        result = {"status": status, "event": event}
        if status == "activo":
            node, visited = self.avl.find(event.key)
            result.update(node_depth=visited - 1, height=node.height,
                          balance=self.avl.balance_factor(node), visited=visited)
        return result

    def known_events(self):
        """Return active and archived events; deleted events are excluded."""
        return {**self.archived, **self.active}

    def candidates_of(self, event):
        return candidates(event, self.known_events().values(), self.W, self.R)

    def _best_reference(self, event):
        chosen = choose_reference(self.candidates_of(event))
        return chosen.event_id if chosen else None

    def refresh_associations(self, changed_id, removed=False):
        """Recompute references affected by an event change or removal."""
        known = self.known_events()
        changed = known.get(changed_id)
        targets = set()
        if not removed and changed is not None:
            targets.add(changed_id)
        for other in known.values():
            if other.reference_id == changed_id:
                targets.add(other.event_id)
            elif (changed is not None and not removed
                  and is_candidate(changed, other, self.W, self.R)):
                targets.add(other.event_id)
        for target_id in targets:
            event = known[target_id]
            event.reference_id = self._best_reference(event)

    def recompute_all_associations(self):
        for event in self.known_events().values():
            event.reference_id = self._best_reference(event)

    def used_as_reference_by(self, event_id):
        return sorted(event.event_id for event in self.known_events().values()
                      if event.reference_id == event_id)

    def advance_clock(self, hours):
        if hours <= 0:
            raise ValidationError("el reloj solo avanza: use un número de horas positivo")
        self.clock = self.clock + timedelta(hours=hours)

    def set_parameters(self, W=None, R=None, L=None, T=None):
        """Validate all parameters before applying them."""
        if W is not None and not W > 0:
            raise ValidationError("W debe ser positivo")
        if R is not None and not R > 0:
            raise ValidationError("R debe ser positivo")
        if T is not None and not T > 0:
            raise ValidationError("T debe ser positivo")
        if L is not None and (isinstance(L, bool) or not isinstance(L, int) or L < 0):
            raise ValidationError("L debe ser un entero no negativo")
        associations_change = ((W is not None and W != self.W)
                               or (R is not None and R != self.R))
        self.W = self.W if W is None else W
        self.R = self.R if R is None else R
        self.L = self.L if L is None else L
        self.T = self.T if T is None else T
        if associations_change:
            self.recompute_all_associations()
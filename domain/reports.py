"""Report processing: one queued report produces one decision."""

from dataclasses import dataclass, field
from datetime import datetime

from domain.models import (ValidationError, format_id, format_time, parse_id,
                           parse_time)

REPORT_FIELDS = ("station", "event_id", "revision", "magnitude", "depth",
                 "x", "y", "time")


@dataclass(frozen=True)
class Report:
    station: str
    event_id: object
    revision: object
    magnitude: object
    depth: object
    x: object
    y: object
    time: object

    def to_dict(self):
        data = {name: getattr(self, name) for name in REPORT_FIELDS}
        if isinstance(data["time"], datetime):
            data["time"] = format_time(parse_time(data["time"]))
        return data

    @staticmethod
    def from_dict(data):
        return Report(**{name: data[name] for name in REPORT_FIELDS})


@dataclass
class ReportResult:
    report: Report
    decision: str
    message: str
    event_id: int | None = None
    key_changed: bool = False
    rotations: int = 0
    cases: dict = field(default_factory=dict)


def _parse_revision(value):
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError("la revisión debe ser un entero positivo")
    return value


def _data_of(report):
    return {"magnitude": report.magnitude, "depth": report.depth,
            "x": report.x, "y": report.y, "time": report.time}


def process_report(catalog, report):
    """Resolve one report and return its decision and AVL operation metrics."""
    stats_before = dict(catalog.avl.stats)
    catalog.counters["reports_processed"] += 1
    result = _decide(catalog, report)
    after = catalog.avl.stats
    result.rotations = ((after["left_rotations"] - stats_before["left_rotations"])
                        + (after["right_rotations"] - stats_before["right_rotations"]))
    result.cases = {key: after[key] - stats_before[key]
                    for key in ("LL", "RR", "LR", "RL")}
    return result


def _decide(catalog, report):
    counters = catalog.counters

    def reject(decision, message, event_id=None):
        counters["discarded"] += 1
        return ReportResult(report, decision, message, event_id)

    try:
        event_id = parse_id(report.event_id)
        revision = _parse_revision(report.revision)
        catalog.check_station(report.station)
    except ValidationError as error:
        return reject("invalido", f"Reporte inválido: {error}")
    name = format_id(event_id)

    status = catalog.status_of(event_id)
    if status == "eliminado":
        return reject("rechazado", f"{name} fue eliminado: el reporte se rechaza "
                      "hasta deshacer la eliminación", event_id)

    if status is None:
        try:
            event = catalog.create(event_id, report.magnitude, report.depth, report.x,
                                   report.y, report.time, report.station, revision)
        except ValidationError as error:
            return reject("invalido", f"Datos inválidos para {name}: {error}", event_id)
        return ReportResult(report, "alta",
                            f"Evento nuevo {name} (revisión {revision}, "
                            f"prioridad {event.priority})", event_id)

    event = catalog.active.get(event_id) or catalog.archived[event_id]
    if revision < event.revision:
        return reject("antiguo", f"Reporte antiguo: revisión {revision} < vigente "
                      f"{event.revision}; {name} no cambia", event_id)
    try:
        data = catalog.validate_data(**_data_of(report))
    except ValidationError as error:
        return reject("invalido", f"Datos inválidos para {name}: {error}", event_id)

    if revision == event.revision:
        if event.same_physical_data(**data):
            added = catalog.confirm(event_id, report.station)
            counters["confirmations"] += 1
            extra = "estación añadida" if added else "la estación ya figuraba"
            return ReportResult(report, "confirmado",
                                f"Confirmación de {name}: {extra}", event_id)
        counters["conflicts"] += 1
        return ReportResult(report, "conflicto",
                            f"Conflicto en {name}: misma revisión {revision} con "
                            "datos distintos; reporte rechazado", event_id)

    old_key = event.key
    new, reactivated = catalog.revise(event_id, revision, report.station, **data)
    changed = reactivated or new.key != old_key
    if reactivated:
        return ReportResult(report, "reactivado",
                            f"{name} reactivado desde el histórico con la "
                            f"revisión {revision} (prioridad {new.priority})",
                            event_id, True)
    detail = (f"clave {tuple(old_key.as_tuple())} -> {tuple(new.key.as_tuple())}"
              if changed else "la clave no cambió")
    return ReportResult(report, "corregido",
                        f"{name} actualizado a la revisión {revision}: {detail}",
                        event_id, changed)
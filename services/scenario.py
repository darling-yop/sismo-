"""Facade that makes each user action atomic and undoable."""

from core.fifo import Queue
from domain.archive import execute_archive, plan_archive
from domain.audit import audit_catalog
from domain.catalog import Catalog
from domain.models import ValidationError, format_id, parse_id
from domain.reports import Report, process_report
from services.history import History
from services.snapshot import capture, restore


class Scenario:
    def __init__(self, zones=None, stations=None, clock=None, history_limit=200):
        self.catalog = Catalog(zones, stations, clock)
        self.queue = Queue()
        self.history = History(history_limit)
        self.paused = False

    def _load(self, data):
        self.catalog, self.queue = restore(data)

    def _run(self, label, action, summarize=None):
        before = capture(self.catalog, self.queue)
        try:
            result = action()
        except Exception:
            self._load(before)
            raise
        summary = summarize(result) if summarize else ""
        self.history.push(label, before, summary, self._metric_delta(before))
        return result

    def _metric_delta(self, before):
        now = {**self.catalog.counters, **self.catalog.avl.stats}
        old = {**before["counters"], **before["rotation_stats"]}
        return {key: now[key] - old.get(key, 0)
                for key in now if now[key] != old.get(key, 0)}

    @staticmethod
    def _name(event_id):
        try:
            return format_id(parse_id(event_id))
        except ValidationError:
            return str(event_id)

    def snapshot(self):
        return capture(self.catalog, self.queue)

    def create_event(self, event_id, magnitude, depth, x, y, time, station):
        return self._run(f"Alta {self._name(event_id)}",
                         lambda: self.catalog.create(event_id, magnitude, depth,
                                                     x, y, time, station))

    def correct_event(self, event_id, **changes):
        return self._run(f"Corrección {self._name(event_id)}",
                         lambda: self.catalog.correct(event_id, **changes))

    def mark_reviewed(self, event_id):
        return self._run(f"Revisado {self._name(event_id)}",
                         lambda: self.catalog.mark_reviewed(event_id))

    def delete_event(self, event_id):
        return self._run(f"Eliminación {self._name(event_id)}",
                         lambda: self.catalog.delete(event_id))

    def advance_clock(self, hours):
        return self._run(f"Reloj +{hours} h", lambda: self.catalog.advance_clock(hours))

    def set_parameters(self, W=None, R=None, L=None, T=None):
        return self._run("Cambio de parámetros",
                         lambda: self.catalog.set_parameters(W, R, L, T))

    def set_stress(self, enabled):
        """Enter stress mode, or leave it only if the AVL audit passes."""
        def action():
            avl = self.catalog.avl
            if enabled == avl.stress:
                raise ValidationError("el modo solicitado ya está activo")
            if not enabled and not audit_catalog(self.catalog)["balanced"]:
                raise ValidationError("el árbol no está equilibrado: "
                                      "use la recuperación global")
            avl.stress = enabled
        return self._run("Modo estrés" if enabled else "Modo normal", action)

    def recover(self):
        """Recover a stress-mode AVL, audit it, and pause continuous processing."""
        def action():
            avl = self.catalog.avl
            if not avl.stress:
                raise ValidationError("la recuperación solo aplica en modo estrés")
            self.paused = True
            report = avl.recover()
            audit = audit_catalog(self.catalog)
            if not audit["balanced"]:
                raise ValidationError("la auditoría no confirma el equilibrio")
            avl.stress = False
            report["mode_after"] = "normal"
            return report
        return self._run("Recuperación global", action,
                         lambda report: f"{report['rotations']} giros, "
                                        f"altura {report['height_after']}")

    def resume(self):
        self.paused = False

    def enqueue_reports(self, reports):
        """Queue a report burst as one undoable action."""
        reports = list(reports)
        if not reports or not all(isinstance(report, Report) for report in reports):
            raise ValidationError("se requiere al menos un reporte válido")

        def action():
            for report in reports:
                self.queue.enqueue(report)
            return len(reports)
        return self._run(f"Ráfaga de {len(reports)} reporte(s)", action)

    def step(self, continuous=False):
        """Process exactly one queued report as one undoable action."""
        if continuous and self.paused:
            raise ValidationError("el procesamiento continuo está en pausa")
        if self.queue.is_empty():
            raise ValidationError("la cola está vacía")
        report = self.queue.peek()
        label = (f"Paso de cola: {report.station} / "
                 f"{self._name(report.event_id)} rev {report.revision}")

        def action():
            return process_report(self.catalog, self.queue.dequeue())
        return self._run(label, action, lambda result: result.decision)

    def preview_archive(self):
        return plan_archive(self.catalog)

    def archive_branch(self):
        plan = plan_archive(self.catalog)
        if plan is None:
            raise ValidationError("no existe una rama elegible; el estado se conserva")
        return self._run(f"Archivo de rama {format_id(plan.root_id)}",
                         lambda: (execute_archive(self.catalog, plan), plan)[1],
                         lambda archive_plan: f"{archive_plan.count} evento(s)")

    def restore_state(self, data, label):
        """Replace the full scenario state as one undoable action."""
        return self._run(label, lambda: self._load(data))

    def undo(self):
        if self.history.is_empty():
            raise ValidationError("no hay acciones para deshacer")
        entry = self.history.pop()
        self._load(entry["before"])
        return entry["label"]
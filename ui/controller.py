"""UI controller: every screen calls this class and never touches the domain.

It has no Tkinter code, so it is unit tested. Each action returns an Outcome
(ok, message in Spanish). The message says WHAT happened and WHY.
Dependencies: ui -> services -> domain -> core.
"""

from dataclasses import dataclass

from domain import comparison, queries
from domain.audit import audit_catalog
from domain.metrics import indicators, node_depths, traversals
from domain.models import ValidationError, format_id, format_time, parse_id
from domain.priority import compute_priority, is_populated
from services import persistence
from services.persistence import PersistenceError
from services.scenario import Scenario
from ui.layout import layout_tree

PRIORITY_NAMES = {3: "alta", 2: "media", 1: "baja"}
CASE_NAMES = ("LL", "RR", "LR", "RL")


@dataclass
class Outcome:
    ok: bool
    message: str
    data: object = None


def sid(event_id):
    return format_id(event_id)


def key_text(key):
    p, m, i = key
    return f"(P={p}, M={m}, I={i})"


def explain_priority(event, zones):
    """Why an event has its priority (assignment section 4)."""
    m, h = event.magnitude, event.depth
    populated = is_populated(event.x, event.y, zones)
    zone = "zona poblada" if populated else "zona no poblada"
    if m >= 6.0:
        return f"prioridad alta: M={m} >= 6,0"
    if m >= 4.5 and h <= 30.0 and populated:
        return f"prioridad alta: M={m} >= 4,5, H={h} <= 30,0 km y {zone}"
    if m >= 4.5:
        why = []
        if h > 30.0:
            why.append(f"H={h} > 30,0 km")
        if not populated:
            why.append("epicentro fuera de zona poblada")
        return f"prioridad media: M={m} >= 4,5 pero " + " y ".join(why)
    return f"prioridad baja: M={m} < 4,5"


def format_event(event, status=None):
    parts = [f"{sid(event.event_id)}  M={event.magnitude}  H={event.depth} km  "
             f"epicentro=({event.x}, {event.y})  hora={format_time(event.time)}",
             f"revisión={event.revision}  atención={event.attention}  "
             f"estaciones={', '.join(sorted(event.stations))}  "
             f"clave={key_text(event.key.as_tuple())}"]
    if status:
        parts.insert(0, f"Estado: {status}")
    if event.reference_id is not None:
        parts.append(f"referencia: {sid(event.reference_id)}")
    return "\n".join(parts)


class Controller:
    def __init__(self, scenario=None):
        self.sc = scenario or Scenario()
        self.load_order = []          # ids in the order of the last insertion load

    # ---------- small helpers ----------

    @property
    def catalog(self):
        return self.sc.catalog          # always fresh: undo REPLACES it

    @property
    def queue(self):
        return self.sc.queue

    def _guard(self, action):
        try:
            return action()
        except PersistenceError as error:
            lines = "\n".join(f"  - {p}" for p in error.problems)
            return Outcome(False, "Archivo rechazado; el escenario anterior se conserva.\n" + lines,
                           error.problems)
        except ValidationError as error:
            return Outcome(False, f"No se pudo realizar la operación: {error}")

    def _rotations(self):
        s = self.catalog.avl.stats
        return s["left_rotations"] + s["right_rotations"], dict(s)

    def _rot_text(self, before):
        now_total, now = self._rotations()
        total = now_total - before[0]
        cases = {k: now[k] - before[1][k] for k in CASE_NAMES if now[k] != before[1][k]}
        if self.catalog.avl.stress:
            return "modo estrés: sin giros (aplazados)" if total == 0 else f"{total} giro(s)"
        if total == 0:
            return "sin giros (el árbol ya cumplía AVL)"
        detail = ", ".join(f"{k}×{v}" for k, v in cases.items())
        return f"{total} giro(s) elemental(es) [{detail}]"

    # ---------- reading: event details ----------

    def describe(self, event_id):
        def run():
            info = self.catalog.lookup(event_id)
            if info["status"] is None:
                raise ValidationError("el identificador no existe")
            text = format_event(info["event"], info["status"])
            text += "\n" + explain_priority(info["event"], self.catalog.zones)
            if info["status"] == "activo":
                text += (f"\nNodo: profundidad={info['node_depth']}  altura={info['height']}  "
                         f"balance={info['balance']}  nodos visitados al buscar={info['visited']}")
                if info["event"].priority == 3 and info["node_depth"] > self.catalog.L:
                    text += f"\nACCESO COSTOSO: profundidad {info['node_depth']} > L={self.catalog.L}"
            used = self.catalog.used_as_reference_by(info["event"].event_id)
            if used:
                text += "\nLo usan como referencia: " + ", ".join(sid(i) for i in used)
            return Outcome(True, text, info)
        return self._guard(run)

    def preview_delete(self, event_id):
        def run():
            eid = parse_id(event_id)
            event = self.catalog.active.get(eid)
            if event is None:
                raise ValidationError("solo se puede eliminar un evento activo")
            node = self.catalog.avl.find(event.key)[0]
            kids = [c.key.event_id for c in (node.left, node.right) if c is not None]
            used = self.catalog.used_as_reference_by(eid)
            text = ("Se eliminará SOLO este evento:\n" + format_event(event) +
                    f"\nSus {len(kids)} hijo(s) directo(s) "
                    f"({', '.join(sid(i) for i in kids) or 'ninguno'}) y todos los demás "
                    "descendientes permanecen en el catálogo.")
            text += ("\nEl árbol se reorganiza según el modo " +
                     ("estrés (solo orden, sin giros)." if self.catalog.avl.stress
                      else "normal (se restablece el balance)."))
            if used:
                text += "\nSe recalcularán las referencias de: " + ", ".join(sid(i) for i in used)
            return Outcome(True, text)
        return self._guard(run)

    def preview_correction(self, event_id, changes):
        def run():
            eid = parse_id(event_id)
            old = self.catalog.active.get(eid)
            if old is None:
                raise ValidationError("solo se puede corregir un evento activo")
            merged = {n: getattr(old, n) for n in ("magnitude", "depth", "x", "y", "time")}
            merged.update(changes)
            data = self.catalog.validate_data(**merged)
            populated = is_populated(data["x"], data["y"], self.catalog.zones)
            new_p = compute_priority(data["magnitude"], data["depth"], populated)
            new_key = (new_p, data["magnitude"], eid)
            text = ("Evento a corregir:\n" + format_event(old) +
                    f"\nNueva clave prevista: {key_text(new_key)}; revisión {old.revision} -> "
                    f"{old.revision + 1}")
            if new_key != old.key.as_tuple():
                text += "\nLa clave cambia: el nodo se retira del AVL y se reinserta en su nueva posición."
            else:
                text += "\nLa clave no cambia: el nodo conserva su posición."
            return Outcome(True, text)
        return self._guard(run)

    # ---------- event actions ----------

    def create(self, event_id, magnitude, depth, x, y, time, station):
        def run():
            before = self._rotations()
            event = self.sc.create_event(event_id, magnitude, depth, x, y, time, station)
            info = self.catalog.lookup(event.event_id)
            msg = (f"Alta de {sid(event.event_id)}: {explain_priority(event, self.catalog.zones)}. "
                   f"Clave {key_text(event.key.as_tuple())}; insertado a profundidad "
                   f"{info['node_depth']}; {self._rot_text(before)}.")
            if event.reference_id is not None:
                msg += f" Referencia asignada: {sid(event.reference_id)}."
            return Outcome(True, msg, event.event_id)
        return self._guard(run)

    def correct(self, event_id, changes):
        def run():
            old = self.catalog.active.get(parse_id(event_id))
            old_key = old.key.as_tuple() if old else None
            before = self._rotations()
            new = self.sc.correct_event(event_id, **changes)
            moved = new.key.as_tuple() != old_key
            msg = (f"Corrección de {sid(new.event_id)} (revisión {new.revision}): "
                   f"{explain_priority(new, self.catalog.zones)}. ")
            msg += (f"La clave pasó de {key_text(old_key)} a {key_text(new.key.as_tuple())}: "
                    f"se retiró y reinsertó el nodo; {self._rot_text(before)}." if moved
                    else "La clave no cambió: el nodo no se movió.")
            return Outcome(True, msg, new.event_id)
        return self._guard(run)

    def review(self, event_id):
        def run():
            event = self.sc.mark_reviewed(event_id)
            return Outcome(True, f"{sid(event.event_id)} marcado como revisado. "
                           "P, M e I no cambian: el nodo no se mueve.")
        return self._guard(run)

    def delete(self, event_id):
        def run():
            before = self._rotations()
            event = self.sc.delete_event(event_id)
            return Outcome(True, f"{sid(event.event_id)} eliminado: solo ese evento sale del AVL "
                           f"y su identificador queda retirado; {self._rot_text(before)}.")
        return self._guard(run)

    def advance_clock(self, hours):
        def run():
            h = float(hours)
            self.sc.advance_clock(h)
            return Outcome(True, f"Reloj avanzado {h} h: ahora {format_time(self.catalog.clock)}. "
                           "Cambia la antigüedad de los eventos (archivo de ramas).")
        try:
            float(hours)
        except (TypeError, ValueError):
            return Outcome(False, "las horas deben ser un número")
        return self._guard(run)

    def set_parameters(self, W, R, L, T):
        def run():
            def num(v, name, integer=False):
                if v in (None, ""):
                    return None
                try:
                    return int(v) if integer else float(v)
                except ValueError:
                    raise ValidationError(f"{name} debe ser un número{' entero' if integer else ''}")
            self.sc.set_parameters(num(W, "W"), num(R, "R"), num(L, "L", True), num(T, "T"))
            c = self.catalog
            return Outcome(True, f"Parámetros: W={c.W} h, R={c.R} km, L={c.L}, T={c.T} h. "
                           "Se recalcularon asociaciones y marcas de acceso costoso.")
        return self._guard(run)

    # ---------- mode and recovery ----------

    def set_stress(self, enabled):
        def run():
            self.sc.set_stress(enabled)
            return Outcome(True, "Modo estrés activado: se conserva el orden BST y se aplazan "
                           "las rotaciones; el árbol puede dejar de ser AVL." if enabled else
                           "Modo normal: la auditoría confirmó el equilibrio.")
        return self._guard(run)

    def recover(self):
        def run():
            r = self.sc.recover()
            cases = ", ".join(f"{k}×{v}" for k, v in r["cases"].items() if v) or "ninguno"
            return Outcome(True,
                           f"Recuperación global: cola en pausa; {r['imbalanced_before']} nodo(s) "
                           f"desbalanceado(s), diferencia máxima {r['max_gap_before']}; "
                           f"{r['rotations']} giro(s) elemental(es) (casos: {cases}); "
                           f"desbalanceados después: {r['imbalanced_after']}; altura final "
                           f"{r['height_after']}. La auditoría confirma el equilibrio y vuelve el modo "
                           "normal. La cola sigue en pausa hasta pulsar Reanudar.", r)
        return self._guard(run)

    def resume(self):
        self.sc.resume()
        return Outcome(True, "Procesamiento reanudado.")

    # ---------- queue ----------

    def queue_rows(self):
        return [(i, r.station, r.event_id, r.revision, r.magnitude, r.depth, r.x, r.y,
                 r.time if isinstance(r.time, str) else format_time(r.time))
                for i, r in enumerate(self.queue.to_list(), start=1)]

    def enqueue(self, rows):
        """rows: list of dicts with the Report fields (as typed by the user)."""
        from domain.reports import Report
        def run():
            reports = []
            for index, row in enumerate(rows, start=1):
                try:
                    reports.append(Report.from_dict(row))
                except KeyError as error:
                    raise ValidationError(f"reporte #{index}: falta el campo {error}")
            self.sc.enqueue_reports(reports)
            return Outcome(True, f"{len(reports)} reporte(s) en la cola FIFO, en orden de recepción. "
                           "Aún no se aplican: use Paso o Continuo.")
        return self._guard(run)

    def step(self, continuous=False):
        def run():
            report = self.queue.peek() if not self.queue.is_empty() else None
            before = self._rotations()
            result = self.sc.step(continuous)
            r = report
            text = (f"Estación {r.station} · evento {sid(result.event_id) if result.event_id else r.event_id}"
                    f" · revisión {r.revision} -> decisión: {result.decision.upper()}. "
                    f"{result.message}. Giros: {self._rot_text(before)}.")
            return Outcome(True, text, result)
        return self._guard(run)

    # ---------- archive ----------

    def preview_archive(self):
        def run():
            plan = self.sc.preview_archive()
            if plan is None:
                return Outcome(False, "No existe una rama elegible (prioridad baja y antigüedad "
                               f"> T={self.catalog.T} h en todos sus eventos). El estado se conserva.")
            text = (f"Rama elegida: raíz {sid(plan.root_id)} con {plan.count} evento(s):\n  " +
                    ", ".join(sid(i) for i in plan.ids) +
                    f"\nJustificación: {plan.justification}\n"
                    f"Ramas elegibles (raíz, tamaño, profundidad): "
                    + "; ".join(f"{sid(r)}, {s}, {d}" for r, s, d in plan.eligible))
            return Outcome(True, text, plan)
        return self._guard(run)

    def archive(self):
        def run():
            before = self._rotations()
            plan = self.sc.archive_branch()
            return Outcome(True, f"Archivo de rama {sid(plan.root_id)}: {plan.count} evento(s) "
                           f"pasan al histórico (conservan datos e identidad). {self._rot_text(before)}. "
                           "Se deshace con una sola acción.")
        return self._guard(run)

    def undo(self):
        def run():
            label = self.sc.undo()
            return Outcome(True, f"Deshecho: {label}. Estado anterior restaurado "
                           "(topología, cola, reloj, parámetros y métricas).")
        return self._guard(run)

    # ---------- files and versions ----------

    def export_state(self, path):
        return self._guard(lambda: (persistence.save_state(self.sc, path),
                                    Outcome(True, f"Estado guardado en {path}"))[1])

    def import_topology(self, path):
        def run():
            info = persistence.load_topology(self.sc, path)
            msg = "Carga por topología completa: el árbol se reconstruyó enlace por enlace."
            if info["mode"] == "stress":
                msg += " ATENCIÓN: topología cargada en MODO ESTRÉS (puede estar desbalanceada)."
            for w in info["warnings"]:
                msg += f"\n  aviso: {w}"
            return Outcome(True, msg, info)
        return self._guard(run)

    def import_insertions(self, path):
        def run():
            info = persistence.load_insertions(self.sc, path)
            self.load_order = info["order"]
            a, b = info["comparison"]["avl"], info["comparison"]["bst"]
            return Outcome(True,
                           f"Carga por inserciones: {a['size']} eventos, mismo orden en AVL y BST. "
                           f"AVL altura {a['height']}, hojas {a['leaves']}; BST altura {b['height']}, "
                           f"hojas {b['leaves']}. Vea la pestaña Comparación.", info)
        return self._guard(run)

    def import_reports(self, path):
        def run():
            reports = persistence.load_reports(path)
            self.sc.enqueue_reports(reports)
            return Outcome(True, f"{len(reports)} reporte(s) del archivo agregados a la cola.")
        return self._guard(run)

    def save_version(self, name, folder=persistence.DEFAULT_VERSIONS_DIR):
        return self._guard(lambda: Outcome(True, "Versión guardada: " + persistence.save_version(
            self.sc, name, folder)))

    def versions(self, folder=persistence.DEFAULT_VERSIONS_DIR):
        return persistence.list_versions(folder)

    def restore_version(self, name, folder=persistence.DEFAULT_VERSIONS_DIR):
        def run():
            info = persistence.restore_version(self.sc, name, folder)
            return Outcome(True, f"Versión '{name}' restaurada (acción deshacible)."
                           + (" Modo estrés." if info["mode"] == "stress" else ""))
        return self._guard(run)

    # ---------- audit, indicators, queries ----------

    def audit(self):
        a = audit_catalog(self.catalog)
        lines = [f"Modo: {a['mode']}   nodos: {a['nodes']}   "
                 f"resultado: {'CORRECTO' if a['ok'] else 'CON ERRORES'}"]
        if a["expected_imbalance"]:
            lines.append(f"Desbalance esperado (modo estrés): {len(a['expected_imbalance'])} nodo(s), "
                         f"diferencia máxima {a['max_imbalance']}")
            for item in a["expected_imbalance"][:15]:
                lines.append(f"  {sid(item['event_id'])}: factor {item['balance']}")
        for eid, problems in a["by_event"].items():
            lines.append(f"Evento {sid(eid) if eid else '(global)'}:")
            lines.extend(f"    - {p}" for p in problems)
        if a["ok"]:
            lines.append("Orden global por K, unicidad, referencias, alturas y factores: sin errores."
                         + ("" if a["balanced"] else " El árbol no cumple AVL (esperado en estrés)."))
        return Outcome(a["ok"], "\n".join(lines), a)

    def indicators_text(self):
        i = indicators(self.catalog, self.queue)
        c, r, p = i["counters"], i["rotations"], i["by_priority"]
        lines = [f"Modo: {i['mode']}",
                 f"Activos: {i['active']}   Histórico: {i['archived']}   Eliminados: {i['deleted']}",
                 f"Altura: {i['height']}   Hojas: {i['leaves']}   Cola: {i['queue']}",
                 f"Prioridad alta/media/baja: {p[3]}/{p[2]}/{p[1]}   Pendientes: {i['pending']}   "
                 f"Acceso costoso: {i['costly_access']}",
                 f"Correcciones: {c['corrections']}   Confirmaciones: {c['confirmations']}   "
                 f"Conflictos: {c['conflicts']}   Descartados: {c['discarded']}",
                 f"Archivos masivos: {c['mass_archives']}   Eventos archivados: {c['archived_events']}   "
                 f"Reportes procesados: {c['reports_processed']}",
                 f"Casos LL/RR/LR/RL: {r['LL']}/{r['RR']}/{r['LR']}/{r['RL']}   "
                 f"Giros simples izq/der: {r['left_rotations']}/{r['right_rotations']}"]
        return "\n".join(lines)

    def traversal_text(self):
        t = traversals(self.catalog.avl)
        names = {"inorder": "Inorden", "preorder": "Preorden", "postorder": "Postorden",
                 "level_order": "Por niveles"}
        out = []
        for key, label in names.items():
            ids = [sid(k[2])[4:].lstrip("0") or "0" for k in t[key]]
            out.append(f"{label}: " + " ".join(ids))
        return "\n".join(out)

    def history_rows(self):
        return [(i, e["label"], e["summary"],
                 ", ".join(f"{k}:{v:+d}" for k, v in e["metrics"].items()))
                for i, e in enumerate(self.sc.history.log(), start=1)]

    def query(self, name, **args):
        def run():
            fn = {"top": lambda: queries.top_pending(self.catalog, int(args["k"])),
                  "magnitude": lambda: queries.by_magnitude(self.catalog, args["low"], args["high"]),
                  "dates": lambda: queries.shallow_in_dates(self.catalog, args["depth"],
                                                           args["start"], args["end"]),
                  "associations": lambda: queries.associations(self.catalog, args["id"]),
                  "costly": lambda: queries.costly_access(self.catalog)}[name]
            try:
                result = fn()
            except ValueError as error:
                if isinstance(error, ValidationError):
                    raise
                raise ValidationError("k debe ser un entero positivo")
            return Outcome(True, self.format_query(name, result), result)
        return self._guard(run)

    def format_query(self, name, result):
        lines = []
        if name == "associations":
            ev = result["event"]
            lines.append(f"Evento consultado: {sid(ev.event_id)} ({result['status']})")
            show = lambda t: f"{sid(t[0].event_id)} [{t[1]}] M={t[0].magnitude} {format_time(t[0].time)}"
            lines.append("Candidatos: " + (" | ".join(show(t) for t in result["candidates"]) or "ninguno"))
            lines.append("Referencia elegida: " + (show(result["reference"]) if result["reference"] else "ninguna"))
            lines.append("Lo usan como referencia: " + (" | ".join(show(t) for t in result["used_by"]) or "nadie"))
        elif name == "costly":
            for row in result["results"]:
                lines.append(f"{sid(row['event'].event_id)}  profundidad nodo={row['depth']}  "
                             f"L={row['limit']}  nodos visitados={row['visited']}")
            if not result["results"]:
                lines.append("Ningún evento de prioridad alta supera el límite L.")
        else:
            for e in result["results"]:
                lines.append(f"{sid(e.event_id)}  P={e.priority}  M={e.magnitude}  H={e.depth}  "
                             f"{format_time(e.time)}  atención={e.attention}")
            if not result["results"]:
                lines.append("Sin resultados.")
        lines.append(f"\nNodos del AVL examinados: {result['examined']}\n{result['note']}")
        return "\n".join(lines)

    # ---------- view models ----------

    def event_rows(self):
        c = self.catalog
        depths = node_depths(c.avl)
        costly = {r["event"].event_id for r in queries.costly_access(c)["results"]}
        rows = []
        for status, group in (("activo", c.active), ("archivado", c.archived),
                              ("eliminado", c.deleted)):
            for e in sorted(group.values(), key=lambda e: e.key.as_tuple(), reverse=True):
                rows.append((sid(e.event_id), status, e.priority, e.magnitude, e.depth, e.x, e.y,
                             format_time(e.time), e.revision, e.attention,
                             depths.get(e.event_id, "") if status == "activo" else "",
                             "SÍ" if e.event_id in costly else "",
                             sid(e.reference_id) if e.reference_id else ""))
        return rows

    def tree_view(self, max_depth=12):
        """Everything the AVL screen needs in one call."""
        c = self.catalog
        audit = audit_catalog(c)
        costly = {r["event"].event_id for r in queries.costly_access(c)["results"]}
        banner = ""
        if c.avl.stress:
            n = len(audit["expected_imbalance"])
            banner = ("MODO ESTRÉS: rotaciones aplazadas. " +
                      (f"El árbol NO cumple AVL ({n} nodo(s) desbalanceado(s), "
                       f"diferencia máxima {audit['max_imbalance']})." if n else
                       "Por ahora el árbol cumple AVL, pero puede degradarse."))
        elif not audit["ok"]:
            banner = f"AUDITORÍA CON {len(audit['errors'])} ERROR(ES): use Verificar estructura."
        return {"layout": layout_tree(c.avl, max_depth), "costly": costly,
                "events": c.active, "stress": c.avl.stress, "banner": banner,
                "imbalanced": {i["event_id"] for i in audit["expected_imbalance"]}}

    def comparison_view(self, order_name="ascending", max_depth=12):
        """AVL (live tree) and a BST built with the same keys in the chosen order."""
        keys = [e.key for e in self.catalog.active.values()]
        if not keys:
            return Outcome(False, "No hay eventos activos para comparar.")
        orders = comparison.insertion_orders(sorted(keys, key=lambda k: k.event_id))
        if order_name == "file" and self.load_order:
            by_id = {k.event_id: k for k in keys}
            orders["file"] = [by_id[i] for i in self.load_order if i in by_id]
        chosen = orders.get(order_name)
        if not chosen:
            return Outcome(False, "orden de inserción desconocido")
        avl, bst = comparison.build(chosen)
        stats = {"avl": comparison.tree_stats(avl, chosen), "bst": comparison.tree_stats(bst, chosen)}
        return Outcome(True, "", {"avl": layout_tree(avl, max_depth), "bst": layout_tree(bst, max_depth),
                                  "stats": stats, "orders": list(orders), "n": len(chosen)})

    def plane_view(self):
        c = self.catalog
        costly = {r["event"].event_id for r in queries.costly_access(c)["results"]}
        return {"zones": c.zones, "active": list(c.active.values()),
                "archived": list(c.archived.values()), "costly": costly}

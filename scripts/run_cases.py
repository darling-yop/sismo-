"""Section 16 cases: expected vs obtained, reproducible.

    python -m scripts.run_cases          # prints a table and writes docs/casos_seccion16.md
Each row compares a value decided by hand (expected) with what the program
produced (obtained). Initial state of every case: see `INITIAL_STATE`.
"""

import os
import tempfile

from domain import queries
from domain.audit import audit_catalog
from domain.models import ValidationError
from domain.reports import Report
from scripts.common import CLOCK, OLD, YOUNG, ZONES, add, new_scenario
from services import persistence
from services.persistence import PersistenceError, write_json
from services.scenario import Scenario

INITIAL_STATE = (
    f"Reloj de simulación {CLOCK}; W=48 h, R=40 km, L=3, T=72 h; estaciones EST-A/B/C; zonas: "
    + "; ".join(f"{z.name} [{z.x1},{z.y1}]-[{z.x2},{z.y2}] {'poblada' if z.populated else 'no poblada'}"
                for z in ZONES)
    + ". Cada caso parte de un escenario vacío salvo que se indique lo contrario.")


class Rows(list):
    def check(self, case, what, expected, obtained):
        self.append({"case": case, "what": what, "expected": expected, "obtained": obtained,
                     "ok": expected == obtained})


def key_of(sc, eid):
    return sc.catalog.active[eid].key.as_tuple()


# ---------- 1. limits and ties ----------

def case_limits(rows):
    c = "1 Límites y empates"
    sc = new_scenario()
    data = [(1, 4.5, 30.0, 300.0, 300.0, 3, "M=4,5, H=30,0 km, zona poblada"),
            (2, 4.5, 30.1, 300.0, 300.0, 2, "M=4,5, H=30,1 km (supera el límite)"),
            (3, 4.5, 10.0, 900.0, 900.0, 2, "M=4,5, H=10, epicentro fuera de zona poblada"),
            (4, 4.4, 10.0, 300.0, 300.0, 1, "M=4,4 (bajo el umbral)"),
            (5, 6.0, 100.0, 900.0, 900.0, 3, "M=6,0 exacto, profundo y sin población"),
            (6, 5.9, 100.0, 900.0, 900.0, 2, "M=5,9 profundo y sin población"),
            (7, 4.5, 30.0, 500.0, 300.0, 3, "epicentro (500,300) sobre el borde Valle(poblada)/Costa"),
            (8, 4.5, 30.0, 500.0, 450.0, 3, "epicentro (500,450) sobre el borde de Valle")]
    for eid, m, h, x, y, expected, label in data:
        add(sc, eid, m, h, x, y)
        rows.check(c, label, f"prioridad {expected}", f"prioridad {sc.catalog.active[eid].priority}")
    for eid in (23, 21, 22):                                # tie: same P and M, ids out of order
        add(sc, eid, 2.0)
    ties = [k.event_id for k in sc.catalog.avl.inorder() if k.priority == 1 and k.magnitude == 2.0]
    rows.check(c, "igual P y M: el desempate es por identificador (inorden)", [21, 22, 23], ties)


# ---------- 2. correction and old report ----------

def case_correction(rows):
    c = "2 Corrección y reporte antiguo"
    sc = new_scenario()
    add(sc, 20, 4.8, 70.0, 300.0, 300.0)
    rows.check(c, "estado inicial M=4,8 H=70,0", "prioridad 2", f"prioridad {sc.catalog.active[20].priority}")
    sc.correct_event(20, magnitude=6.2, depth=15.0)
    e = sc.catalog.active[20]
    rows.check(c, "tras corregir a M=6,2 H=15,0", "prioridad 3, clave (3, 6.2, 20), revisión 2",
               f"prioridad {e.priority}, clave {key_of(sc, 20)}, revisión {e.revision}")
    sc.enqueue_reports([Report("EST-B", 20, 1, 4.8, 70.0, 300.0, 300.0, "2026-09-07T10:00:00Z")])
    result = sc.step()
    rows.check(c, "reporte con revisión menor (1 < 2)", "decisión antiguo", f"decisión {result.decision}")
    rows.check(c, "no se crea otro nodo ni se revierte", "1 nodo, clave (3, 6.2, 20)",
               f"{sc.catalog.avl.size} nodo, clave {key_of(sc, 20)}")
    rows.check(c, "contador de descartados", 1, sc.catalog.counters["discarded"])


# ---------- 3. late report ----------

def case_late_report(rows):
    c = "3 Reporte tardío"
    sc = new_scenario()
    for st, eid, m, x, t in (("EST-A", 1, 5.6, 300.0, "2026-09-07T10:00:00Z"),
                             ("EST-B", 2, 4.2, 305.0, "2026-09-07T10:20:00Z")):
        sc.enqueue_reports([Report(st, eid, 1, m, 10.0, x, 300.0, t)])
        sc.step()
    before = sc.catalog.active[2].reference_id
    rows.check(c, "antes del tardío: referencia de #2 (M4,2)", "#1 (M5,6)", f"#{before} (M5,6)")
    sc.enqueue_reports([Report("EST-C", 3, 1, 6.1, 10.0, 302.0, 300.0, "2026-09-07T09:55:00Z")])
    sc.step()
    cands = [t[0].event_id for t in queries.associations(sc.catalog, 2)["candidates"]]
    rows.check(c, "candidatos de #2 tras el evento M6,1 de las 09:55", [3, 1], cands)
    rows.check(c, "referencia de #2 (mayor magnitud, regla del equipo)", 3, sc.catalog.active[2].reference_id)
    rows.check(c, "referencia de #1 pasa a #3 (6,1 > 5,6 y ocurrió antes)", 3, sc.catalog.active[1].reference_id)
    rows.check(c, "el tardío no tiene referencia", None, sc.catalog.active[3].reference_id)


# ---------- 4. rotations and recovery ----------

def case_rotations(rows):
    c = "4 Rotaciones y recuperación"
    for name, mags in (("LL", (3.0, 2.0, 1.0)), ("RR", (1.0, 2.0, 3.0)),
                       ("LR", (3.0, 1.0, 2.0)), ("RL", (1.0, 3.0, 2.0))):
        sc = new_scenario()
        for i, m in enumerate(mags, start=1):
            add(sc, i, m)
        s = sc.catalog.avl.stats
        rows.check(c, f"caso {name} con magnitudes {mags}",
                   {"caso": 1, "giros": 2 if name in ("LR", "RL") else 1, "raíz": 2 if name in ("LL", "RR") else 3,
                    "balanceado": True},
                   {"caso": s[name], "giros": s["left_rotations"] + s["right_rotations"],
                    "raíz": sc.catalog.avl.root.key.event_id, "balanceado": audit_catalog(sc.catalog)["balanced"]})
    sc = new_scenario(stress=True)
    for i in range(1, 16):                                  # chain: ascending keys, all in stress
        add(sc, i, i / 10, 10.0, 900.0, 900.0, f"2026-09-07T11:{60 - i:02d}:00Z")
    cat = sc.catalog
    ids = sorted(cat.active)
    inorder = [k.event_id for k in cat.avl.inorder()]
    refs = {i: cat.active[i].reference_id for i in ids}
    audit = audit_catalog(cat)
    rows.check(c, "estrés: cadena de 15 nodos (altura 14), desbalance esperado", True,
               audit["ok"] and not audit["balanced"] and audit["max_imbalance"] > 2)
    report = sc.recover()
    cat = sc.catalog
    rows.check(c, "diferencia de altura máxima antes de reparar (> 2)", True, report["max_gap_before"] > 2)
    rows.check(c, "tras recuperar: AVL válido, modo normal", (True, False),
               (audit_catalog(cat)["balanced"], cat.avl.stress))
    rows.check(c, "conserva identidades", ids, sorted(cat.active))
    rows.check(c, "conserva el orden (inorden idéntico)", inorder, [k.event_id for k in cat.avl.inorder()])
    rows.check(c, "conserva las asociaciones", refs, {i: cat.active[i].reference_id for i in ids})
    rows.check(c, "la cola queda en pausa", True, sc.paused)
    rows.check(c, "altura final entre 3 y 4 (cota AVL para 15 nodos)", True, 3 <= cat.avl.height() <= 4)


# ---------- 5. mass archive ----------

def build_stress(specs):
    sc = new_scenario(stress=True)
    for eid, m, when in specs:
        add(sc, eid, m, 10.0, 900.0, 900.0, when)
    return sc


def case_archive(rows):
    c = "5 Archivo masivo"
    sc = build_stress([(100, 5.0, YOUNG), (50, 3.0, OLD), (20, 1.0, OLD), (60, 4.0, OLD)])
    plan = sc.preview_archive()
    rows.check(c, "rama elegible con varios eventos: raíz #50, ids [20, 50, 60]", (50, [20, 50, 60]),
               (plan.root_id, sorted(plan.ids)))
    sc.archive_branch()
    rows.check(c, "tras archivar: activos [100], histórico [20, 50, 60]", ([100], [20, 50, 60]),
               (sorted(sc.catalog.active), sorted(sc.catalog.archived)))
    sc.undo()
    rows.check(c, "deshacer devuelve el estado completo (una sola acción)", ([20, 50, 60, 100], []),
               (sorted(sc.catalog.active), sorted(sc.catalog.archived)))

    sc = build_stress([(50, 3.0, YOUNG), (10, 1.0, OLD), (60, 4.0, YOUNG), (55, 3.5, OLD)])
    rows.check(c, "empate de tamaño (1 y 1): gana la raíz más profunda (#55, prof. 2 > #10, prof. 1)",
               55, sc.preview_archive().root_id)
    sc = build_stress([(50, 3.0, YOUNG), (10, 1.0, OLD), (60, 4.0, OLD)])
    rows.check(c, "empate de tamaño y profundidad: gana el mayor id (#60)", 60, sc.preview_archive().root_id)

    sc = build_stress([(50, 3.0, YOUNG), (10, 1.0, YOUNG)])
    snap = sc.snapshot()
    refused = False
    try:
        sc.archive_branch()
    except ValidationError:
        refused = True
    rows.check(c, "sin ramas elegibles: se informa y el estado se conserva", (None, True, True),
               (sc.preview_archive(), refused, sc.snapshot() == snap))

    sc = new_scenario(stress=True)
    add(sc, 10, 2.0, 10.0, 900.0, 900.0, OLD)                # low priority root, old
    add(sc, 5, 1.0, 10.0, 900.0, 900.0, OLD)
    add(sc, 30, 5.0, 10.0, 900.0, 900.0, OLD)                # medium priority descendant
    plan = sc.preview_archive()
    rows.check(c, "raíz #10 de prioridad baja con descendiente #30 de prioridad media NO es elegible",
               (False, 5), (10 in [r for r, _, _ in plan.eligible], plan.root_id))


# ---------- 6. persistence ----------

def case_persistence(rows):
    c = "6 Persistencia y consistencia"
    with tempfile.TemporaryDirectory() as tmp:
        for stress in (False, True):
            sc = new_scenario(stress)
            for i in range(1, 21):
                add(sc, i, round((i * 7 % 40) / 10, 1), 10.0, 900.0, 900.0, "2026-09-07T10:00:00Z")
            sc.enqueue_reports([Report("EST-A", 99, 1, 1.0, 1.0, 1.0, 1.0, "2026-09-07T10:00:00Z")])
            path = os.path.join(tmp, f"t{stress}.json")
            persistence.save_state(sc, path)
            other = Scenario()
            info = persistence.load_topology(other, path)
            rows.check(c, f"topología {'en estrés' if stress else 'normal'}: mismo estado, topología y modo",
                       (True, True, "stress" if stress else "normal"),
                       (other.snapshot() == sc.snapshot(),
                        other.catalog.avl.preorder() == sc.catalog.avl.preorder(), info["mode"]))
        good = os.path.join(tmp, "tFalse.json")
        doc = persistence.read_json(good)
        doc["state"]["tree"]["nodes"][0]["left"], doc["state"]["tree"]["nodes"][0]["right"] = (
            doc["state"]["tree"]["nodes"][0]["right"], doc["state"]["tree"]["nodes"][0]["left"])
        bad = os.path.join(tmp, "bad.json")
        write_json(bad, doc)
        target = new_scenario()
        add(target, 1, 1.0)
        snap = target.snapshot()
        try:
            persistence.load_topology(target, bad)
            problems = []
        except PersistenceError as error:
            problems = error.problems
        rows.check(c, "archivo inconsistente: rechazado con problemas listados y sin alterar el estado",
                   (True, True), (len(problems) > 0, target.snapshot() == snap))

        a = new_scenario()
        for i in range(1, 11):
            add(a, i, i / 10, 10.0, 900.0, 900.0, "2026-09-07T10:00:00Z")
        a.enqueue_reports([Report("EST-B", 1, 1, 0.1, 10.0, 900.0, 900.0, "2026-09-07T10:00:00Z"),
                           Report("EST-B", 2, 1, 0.2, 10.0, 900.0, 900.0, "2026-09-07T10:00:00Z")])
        persistence.save_version(a, "base", os.path.join(tmp, "v"))
        saved = a.snapshot()
        b = Scenario()                                       # "restart": brand new program state
        persistence.restore_version(b, "base", os.path.join(tmp, "v"))
        rows.check(c, "versión restaurada tras reiniciar", True, b.snapshot() == saved)
        b.correct_event(3, magnitude=6.5)
        b.step()
        rows.check(c, "tras corregir y avanzar la cola: cola 1, #3 con M=6,5", (1, 6.5),
                   (len(b.queue), b.catalog.active[3].magnitude))
        b.undo()
        b.undo()
        rows.check(c, "deshacer paso de cola y corrección: estado idéntico a la versión", True,
                   b.snapshot() == saved)
        b.undo()
        rows.check(c, "deshacer la restauración: escenario vacío", 0, len(b.catalog.active))


CASES = (case_limits, case_correction, case_late_report, case_rotations, case_archive, case_persistence)


def run():
    rows = Rows()
    for case in CASES:
        case(rows)
    return rows


def to_markdown(rows):
    lines = ["# Casos mínimos de la sección 16: esperado vs obtenido", "",
             "Generado con `python -m scripts.run_cases`. " + INITIAL_STATE, "",
             "| Caso | Verificación | Esperado | Obtenido | Resultado |", "|---|---|---|---|---|"]
    for r in rows:
        cell = lambda v: str(v).replace("|", "\\|")
        lines.append(f"| {r['case']} | {cell(r['what'])} | {cell(r['expected'])} | "
                     f"{cell(r['obtained'])} | {'OK' if r['ok'] else '**FALLA**'} |")
    passed = sum(r["ok"] for r in rows)
    lines += ["", f"**{passed} de {len(rows)} verificaciones correctas.**"]
    return "\n".join(lines)


def main():
    rows = run()
    text = to_markdown(rows)
    os.makedirs("docs", exist_ok=True)
    with open(os.path.join("docs", "casos_seccion16.md"), "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(text)
    return all(r["ok"] for r in rows)


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)

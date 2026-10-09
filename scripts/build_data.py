"""Generate the reproducible JSON files in data/. Run from the repo root:
    python -m scripts.build_data
Deterministic: running it twice gives identical files."""

import os
import random

from domain.reports import Report
from scripts.common import CLOCK, OLD, STATIONS, YOUNG, add, new_scenario, zones_json
from services.persistence import save_state, write_json

OUT = "data"


def spread_events(n, seed=7):
    rng = random.Random(seed)
    events = []
    for i in range(1, n + 1):
        events.append({"id": i, "magnitude": round(rng.uniform(0.5, 7.0), 1),
                       "depth": float(rng.randint(2, 120)), "x": float(rng.randint(0, 1000)),
                       "y": float(rng.randint(0, 1000)),
                       "time": f"2026-09-0{rng.randint(3, 7)}T{rng.randint(0, 11):02d}:00:00Z",
                       "station": rng.choice(STATIONS)})
    return events


def insertions(name, events):
    write_json(os.path.join(OUT, name), {"kind": "sismolab-insertions", "clock": CLOCK,
                                         "zones": zones_json(), "stations": STATIONS,
                                         "params": {"W": 48, "R": 40, "L": 3, "T": 72}, "events": events})


def report(station, eid, rev, m, h=10.0, x=300.0, y=300.0, t="2026-09-07T10:00:00Z"):
    return Report(station, eid, rev, m, h, x, y, t).to_dict()


def main():
    events = spread_events(60)
    insertions("carga_inserciones_aleatoria.json", events)

    def key(e):   # ascending K = (P, M, I) is the BST worst case
        from domain.priority import compute_priority, is_populated
        from scripts.common import ZONES
        p = compute_priority(e["magnitude"], e["depth"], is_populated(e["x"], e["y"], ZONES))
        return (p, e["magnitude"], e["id"])
    insertions("carga_inserciones_ascendente.json", sorted(events, key=key))
    insertions("carga_inserciones_descendente.json", sorted(events, key=key, reverse=True))

    normal = new_scenario()
    for e in events[:40]:
        add(normal, e["id"], e["magnitude"], e["depth"], e["x"], e["y"], e["time"], e["station"])
    save_state(normal, os.path.join(OUT, "topologia_normal.json"))

    stress = new_scenario(stress=True)
    for e in sorted(events[:40], key=key):                  # chain: imbalance > 2
        add(stress, e["id"], e["magnitude"], e["depth"], e["x"], e["y"], e["time"], e["station"])
    save_state(stress, os.path.join(OUT, "topologia_estres.json"))

    import json
    with open(os.path.join(OUT, "topologia_normal.json"), encoding="utf-8") as handle:
        bad = json.load(handle)
    nodes = bad["state"]["tree"]["nodes"]
    nodes[0]["left"], nodes[0]["right"] = nodes[0]["right"], nodes[0]["left"]   # breaks BST order
    bad["state"]["active"][0]["priority"] = 3 if bad["state"]["active"][0]["priority"] != 3 else 1
    write_json(os.path.join(OUT, "topologia_inconsistente.json"), bad)

    # initial state for the bursts: 3 known events, empty queue
    base = new_scenario()
    add(base, 1, 4.8, 70.0, 300.0, 300.0, "2026-09-07T08:00:00Z")
    add(base, 2, 3.0, 20.0, 900.0, 900.0, "2026-09-07T09:00:00Z")
    add(base, 3, 5.0, 20.0, 800.0, 100.0, "2026-09-07T07:00:00Z")
    save_state(base, os.path.join(OUT, "estado_inicial_rafaga.json"))
    burst = [report("EST-A", 10, 1, 5.6, 10.0, 300.0, 300.0, "2026-09-07T10:00:00Z"),      # alta
             report("EST-B", 10, 1, 5.6, 10.0, 300.0, 300.0, "2026-09-07T10:00:00Z"),      # confirmación
             report("EST-C", 11, 1, 4.2, 10.0, 305.0, 300.0, "2026-09-07T10:20:00Z"),      # alta
             report("EST-A", 12, 1, 6.1, 10.0, 302.0, 300.0, "2026-09-07T09:55:00Z"),      # alta tardía
             report("EST-B", 1, 2, 6.2, 15.0, 300.0, 300.0, "2026-09-07T08:00:00Z"),       # corrige: P2 -> P3
             report("EST-C", 1, 1, 4.8, 70.0, 300.0, 300.0, "2026-09-07T08:00:00Z"),       # antiguo
             report("EST-A", 10, 1, 5.7, 10.0, 300.0, 300.0, "2026-09-07T10:00:00Z"),      # conflicto
             report("EST-A", 3, 2, 1.0, 5.0, 800.0, 100.0, "2026-09-07T07:00:00Z"),        # corrige: P2 -> P1
             report("EST-X", 4, 1, 3.0),                                                   # estación desconocida
             report("EST-A", 13, 1, 99.0)]                                                 # datos inválidos
    write_json(os.path.join(OUT, "rafaga_mixta.json"), {"kind": "sismolab-reports", "reports": burst})
    print("archivos generados en", OUT)


if __name__ == "__main__":
    main()

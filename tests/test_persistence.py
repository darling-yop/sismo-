import copy
import json
import os
import tempfile
import unittest

from domain.reports import Report
from services.persistence import (PersistenceError, list_versions, load_insertions,
                                  load_topology, restore_version, save_state,
                                  save_version, validate_state, write_json)
from services.scenario import Scenario
from domain.models import ValidationError

T = "2026-09-07T10:00:00Z"


def sample(stress=False, n=30):
    sc = Scenario()
    if stress:
        sc.set_stress(True)
    for i in range(1, n + 1):
        sc.create_event(i, round((i * 7 % 60) / 10, 1), float(i * 3 % 90),
                        float(i * 13 % 900), float(i * 29 % 900), T, "A")
    sc.enqueue_reports([Report("B", 1, 1, 1.0, 1.0, 1.0, 1.0, T)])
    return sc


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def path(self, name):
        return os.path.join(self.dir, name)


class RoundTripTest(TmpCase):
    def test_normal_and_stress_topologies_roundtrip(self):
        for stress in (False, True):
            sc = sample(stress)
            sc.step()
            save_state(sc, self.path("s.json"))
            fresh = Scenario()
            info = load_topology(fresh, self.path("s.json"))
            self.assertEqual(fresh.snapshot(), sc.snapshot())
            self.assertEqual(fresh.catalog.avl.preorder(), sc.catalog.avl.preorder())
            self.assertEqual(info["mode"], "stress" if stress else "normal")
            self.assertEqual(bool(info["warnings"]), stress)
            self.assertEqual(len(fresh.history), 1)          # the load is one action
            fresh.undo()
            self.assertEqual(len(fresh.catalog.active), 0)


class RejectionTest(TmpCase):
    def corrupt(self, mutate, expect):
        sc = sample()
        sc.catalog.avl.stress = False
        doc = {"kind": "sismolab-state", "state": json.loads(json.dumps(sc.snapshot()))}
        mutate(doc["state"])
        write_json(self.path("bad.json"), doc)
        target = sample(n=5)
        before = target.snapshot()
        depth = len(target.history)
        with self.assertRaises(PersistenceError) as ctx:
            load_topology(target, self.path("bad.json"))
        self.assertTrue(any(expect in p for p in ctx.exception.problems),
                        ctx.exception.problems)
        self.assertEqual(target.snapshot(), before)           # state untouched
        self.assertEqual(len(target.history), depth)

    def node(self, state, ident):
        return next(n for n in state["tree"]["nodes"] if n["id"] == ident)

    def test_wrong_order_deep(self):
        def mutate(s):                      # swap two event magnitudes far apart
            a, b = s["active"][0], s["active"][-1]
            a["magnitude"], b["magnitude"] = b["magnitude"], a["magnitude"]
            a["priority"], b["priority"] = b["priority"], a["priority"]
        self.corrupt(mutate, "orden")

    def test_bad_references_and_cycles(self):
        self.corrupt(lambda s: s["tree"]["nodes"][1].update(left=9999), "no existe")
        self.corrupt(lambda s: s["active"][3].update(reference_id=4242), "referencia inválida")
        def cycle(s):
            leaf = next(n for n in s["tree"]["nodes"] if n["left"] is None and n["right"] is None)
            leaf["left"] = s["tree"]["root"]
        self.corrupt(cycle, "ciclo")

    def test_metadata_mismatches(self):
        self.corrupt(lambda s: s["tree"]["nodes"][0].update(height=77), "altura almacenada")
        self.corrupt(lambda s: s["tree"]["nodes"][2].update(balance=5), "factor de balance")
        self.corrupt(lambda s: s["active"][0].update(priority=1 if s["active"][0]["priority"] != 1 else 3),
                     "prioridad almacenada")
        self.corrupt(lambda s: s["counters"].update(corrections=-1), "contadores")

    def test_duplicate_identity_between_active_and_archive(self):
        self.corrupt(lambda s: s["archived"].append(copy.deepcopy(s["active"][0])), "duplicado")

    def test_missing_node_for_active_event(self):
        def mutate(s):
            s["tree"]["nodes"] = [n for n in s["tree"]["nodes"] if n["id"] != 5]
        self.corrupt(mutate, "no tiene nodo")

    def test_unbalanced_topology_needs_stress_mode(self):
        sc = sample(True, n=12)                 # keys ascending-ish in stress
        for i in range(100, 112):
            sc.catalog.create(i, 0.5, 70.0, 1.0, 1.0, T, "A")   # chain at the left end
        self.assertGreater(sc.catalog.avl.height(), 8)
        doc = {"kind": "sismolab-state", "state": sc.snapshot()}
        write_json(self.path("u.json"), doc)
        fresh = Scenario()
        load_topology(fresh, self.path("u.json"))               # mode stress: accepted
        self.assertTrue(fresh.catalog.avl.stress)
        doc["state"]["mode"] = "normal"
        write_json(self.path("n.json"), doc)
        with self.assertRaises(PersistenceError) as ctx:
            load_topology(Scenario(), self.path("n.json"))
        self.assertTrue(any("modo estrés" in p for p in ctx.exception.problems))

    def test_garbage_files(self):
        with open(self.path("g.json"), "w") as f:
            f.write("{not json")
        with self.assertRaises(PersistenceError):
            load_topology(Scenario(), self.path("g.json"))
        write_json(self.path("k.json"), {"kind": "other"})
        with self.assertRaises(PersistenceError):
            load_topology(Scenario(), self.path("k.json"))
        problems, _ = validate_state({"version": 1})
        self.assertTrue(problems)
        problems, _ = validate_state(None)
        self.assertTrue(problems)

    def test_problems_list_every_issue(self):
        sc = sample()
        state = json.loads(json.dumps(sc.snapshot()))
        state["tree"]["nodes"][0]["height"] = 50
        state["active"][1]["reference_id"] = 31337
        problems, _ = validate_state(state)
        self.assertGreaterEqual(len(problems), 2)


class InsertionLoadTest(TmpCase):
    def doc(self, events):
        return {"kind": "sismolab-insertions", "clock": "2026-09-07T12:00:00Z",
                "zones": [], "events": events}

    def ev(self, i, m):
        return {"id": i, "magnitude": m, "depth": 70.0, "x": 1.0, "y": 1.0,
                "time": T, "station": "A"}

    def test_ascending_file_shows_avl_vs_bst(self):
        events = [self.ev(i, 1.0) for i in range(1, 128)]      # ascending keys
        write_json(self.path("i.json"), self.doc(events))
        sc = Scenario()
        out = load_insertions(sc, self.path("i.json"))
        c = out["comparison"]
        self.assertEqual(c["bst"]["height"], 126)
        self.assertEqual(c["avl"]["height"], 6)
        self.assertEqual(c["avl"]["size"], c["bst"]["size"], 127)
        self.assertEqual(sc.catalog.avl.height(), 6)
        self.assertFalse(sc.catalog.avl.stress)
        self.assertEqual(len(sc.history), 1)

    def test_duplicate_or_invalid_events_invalidate_everything(self):
        sc = sample(n=4)
        before = sc.snapshot()
        write_json(self.path("d.json"), self.doc([self.ev(1, 1.0), self.ev(1, 2.0)]))
        with self.assertRaises(PersistenceError) as ctx:
            load_insertions(sc, self.path("d.json"))
        self.assertTrue(any("duplicado" in p for p in ctx.exception.problems))
        write_json(self.path("v.json"), self.doc([self.ev(1, 1.0), self.ev(2, 55.0)]))
        with self.assertRaises(PersistenceError):
            load_insertions(sc, self.path("v.json"))
        self.assertEqual(sc.snapshot(), before)


class VersionTest(TmpCase):
    def test_restore_after_restart_then_undo_correction_and_queue_step(self):
        folder = os.path.join(self.dir, "versions")
        sc = sample(n=20)
        save_version(sc, "Antes de la ráfaga", folder)
        self.assertEqual([v["name"] for v in list_versions(folder)], ["Antes de la ráfaga"])
        with self.assertRaises(ValidationError):
            save_version(sc, "Antes de la ráfaga", folder)
        save_version(sc, "Antes de la ráfaga", folder, overwrite=True)

        restarted = Scenario()                                   # "program restarted"
        restore_version(restarted, "Antes de la ráfaga", folder)
        restored = restarted.snapshot()
        self.assertEqual(restored["queue"], sc.snapshot()["queue"])
        restarted.correct_event(2, magnitude=9.0)
        restarted.step()
        restarted.undo()
        restarted.undo()
        self.assertEqual(restarted.snapshot(), restored)
        restarted.undo()                                         # restore is undoable
        self.assertEqual(len(restarted.catalog.active), 0)

    def test_unknown_or_corrupted_versions(self):
        folder = os.path.join(self.dir, "v")
        with self.assertRaises(ValidationError):
            restore_version(Scenario(), "nada", folder)
        sc = sample(n=5)
        path = save_version(sc, "x", folder)
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        doc["state"]["tree"]["root"] = 12345
        write_json(path, doc)
        target = sample(n=3)
        before = target.snapshot()
        with self.assertRaises(PersistenceError):
            restore_version(target, "x", folder)
        self.assertEqual(target.snapshot(), before)
        with self.assertRaises(ValidationError):
            save_version(sc, "   ", folder)


if __name__ == "__main__":
    unittest.main()

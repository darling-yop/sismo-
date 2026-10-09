import json
import os
import tempfile
import unittest

from domain.models import Zone
from services.persistence import write_json
from services.scenario import Scenario
from ui.controller import Controller, explain_priority

T = "2026-09-07T10:00:00Z"
OLD = "2026-09-01T00:00:00Z"
ZONES = [Zone("Valle", 200.0, 200.0, 500.0, 500.0, True)]


def make():
    return Controller(Scenario(zones=ZONES, stations=["A", "B"]))


def rep(station, eid, rev, m, h=10.0, x=300.0, y=300.0, t=T):
    return dict(station=station, event_id=eid, revision=rev, magnitude=m, depth=h, x=x, y=y, time=t)


class ActionsTest(unittest.TestCase):
    def test_create_explains_priority_and_position(self):
        c = make()
        out = c.create(1, "4.5", "30.0", "300.0", "300.0", T, "A")
        self.assertTrue(out.ok)
        self.assertIn("prioridad alta", out.message)
        self.assertIn("zona poblada", out.message)
        self.assertIn("(P=3, M=4.5, I=1)", out.message)

    def test_validation_error_is_a_message_not_an_exception(self):
        c = make()
        out = c.create(1, "99", "10", "1", "1", T, "A")
        self.assertFalse(out.ok)
        self.assertIn("magnitud", out.message)
        self.assertEqual(len(c.catalog.active), 0)

    def test_correction_changes_key_and_preview_shows_it_first(self):
        c = make()
        c.create(1, "4.8", "70.0", "900.0", "900.0", T, "A")
        pre = c.preview_correction(1, {"magnitude": "6.2", "depth": "15.0"})
        self.assertTrue(pre.ok)
        self.assertIn("(P=3, M=6.2, I=1)", pre.message)
        self.assertEqual(c.catalog.active[1].magnitude, 4.8)      # preview does not modify
        out = c.correct(1, {"magnitude": "6.2", "depth": "15.0"})
        self.assertIn("(P=2, M=4.8, I=1)", out.message)
        self.assertIn("(P=3, M=6.2, I=1)", out.message)

    def test_delete_preview_and_action(self):
        c = make()
        for i, m in enumerate(["1.0", "2.0", "3.0"], start=1):
            c.create(i, m, "10.0", "900.0", "900.0", T, "A")
        pre = c.preview_delete(2)
        self.assertIn("hijo(s) directo(s)", pre.message)
        self.assertIn("SIS-000001", pre.message)
        out = c.delete(2)
        self.assertTrue(out.ok)
        self.assertEqual(sorted(c.catalog.active), [1, 3])
        self.assertFalse(c.preview_delete(2).ok)

    def test_undo_and_params_and_clock(self):
        c = make()
        c.create(1, "1.0", "10.0", "1.0", "1.0", T, "A")
        self.assertTrue(c.set_parameters("50", "", "2", "").ok)
        self.assertEqual((c.catalog.W, c.catalog.L), (50.0, 2))
        self.assertFalse(c.set_parameters("abc", "", "", "").ok)
        self.assertFalse(c.advance_clock("-3").ok)
        self.assertTrue(c.advance_clock("5").ok)
        for _ in range(3):
            self.assertTrue(c.undo().ok)
        self.assertEqual(len(c.catalog.active), 0)
        self.assertFalse(c.undo().ok)

    def test_describe(self):
        c = make()
        c.create(1, "6.5", "10.0", "300.0", "300.0", T, "A")
        out = c.describe("SIS-000001")
        self.assertIn("profundidad=0", out.message)
        self.assertFalse(c.describe(77).ok)


class QueueModeTest(unittest.TestCase):
    def test_burst_step_decisions_and_rotations_text(self):
        c = make()
        rows = [rep("A", 1, 1, "1.0"), rep("B", 1, 1, "1.0"), rep("A", 1, 1, "2.0"),
                rep("A", 1, 2, "3.0"), rep("B", 1, 1, "1.0")]
        self.assertTrue(c.enqueue(rows).ok)
        self.assertEqual(len(c.queue_rows()), 5)
        decisions = [c.step().data.decision for _ in range(5)]
        self.assertEqual(decisions, ["alta", "confirmado", "conflicto", "corregido", "antiguo"])
        self.assertFalse(c.step().ok)                  # empty queue
        self.assertTrue(c.undo().ok)

    def test_enqueue_missing_field(self):
        c = make()
        self.assertFalse(c.enqueue([{"station": "A"}]).ok)

    def test_stress_banner_recovery_and_pause(self):
        c = make()
        self.assertTrue(c.set_stress(True).ok)
        for i in range(1, 12):
            c.create(i, str(i / 10), "10.0", "900.0", "900.0", T, "A")
        view = c.tree_view()
        self.assertIn("NO cumple AVL", view["banner"])
        self.assertTrue(view["imbalanced"])
        self.assertFalse(c.set_stress(False).ok)       # unbalanced -> refused
        out = c.recover()
        self.assertTrue(out.ok, out.message)
        self.assertIn("Reanudar", out.message)
        self.assertTrue(c.sc.paused)
        c.enqueue([rep("A", 50, 1, "1.0")])
        self.assertFalse(c.step(continuous=True).ok)   # paused
        c.resume()
        self.assertTrue(c.step(continuous=True).ok)
        self.assertEqual(c.tree_view()["banner"], "")


class ArchiveTest(unittest.TestCase):
    def test_no_branch_then_branch_and_undo(self):
        c = make()
        c.create(1, "1.0", "10.0", "900.0", "900.0", T, "A")
        self.assertFalse(c.preview_archive().ok)
        self.assertFalse(c.archive().ok)
        c.advance_clock(100)
        pre = c.preview_archive()
        self.assertTrue(pre.ok)
        self.assertIn("SIS-000001", pre.message)
        self.assertTrue(c.archive().ok)
        self.assertEqual((len(c.catalog.active), len(c.catalog.archived)), (0, 1))
        c.undo()
        self.assertEqual((len(c.catalog.active), len(c.catalog.archived)), (1, 0))


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def test_state_roundtrip_and_rejection_keeps_state(self):
        c = make()
        for i in range(1, 8):
            c.create(i, str(i / 10), "10.0", "900.0", "900.0", T, "A")
        self.assertTrue(c.export_state(self.path("s.json")).ok)
        other = make()
        self.assertTrue(other.import_topology(self.path("s.json")).ok)
        self.assertEqual(other.sc.snapshot(), c.sc.snapshot())
        with open(self.path("s.json"), encoding="utf-8") as handle:
            doc = json.load(handle)
        doc["state"]["active"][0]["priority"] = 3        # inconsistent metadata
        write_json(self.path("bad.json"), doc)
        before = other.sc.snapshot()
        out = other.import_topology(self.path("bad.json"))
        self.assertFalse(out.ok)
        self.assertIn("conserva", out.message)
        self.assertEqual(other.sc.snapshot(), before)

    def test_insertions_reports_and_comparison(self):
        events = [{"id": i, "magnitude": i / 10, "depth": 10.0, "x": 1.0, "y": 1.0, "time": T,
                   "station": "A"} for i in range(1, 41)]
        write_json(self.path("i.json"), {"kind": "sismolab-insertions", "events": events})
        c = Controller()
        out = c.import_insertions(self.path("i.json"))
        self.assertTrue(out.ok, out.message)
        view = c.comparison_view("ascending")
        self.assertTrue(view.ok)
        stats = view.data["stats"]
        self.assertEqual(stats["bst"]["height"], 39)
        self.assertLess(stats["avl"]["height"], 8)
        self.assertTrue(c.comparison_view("file").ok)
        write_json(self.path("r.json"), {"kind": "sismolab-reports", "reports": [rep("A", 1, 1, "1.0")]})
        self.assertTrue(c.import_reports(self.path("r.json")).ok)
        self.assertEqual(len(c.queue_rows()), 1)
        write_json(self.path("r2.json"), {"kind": "sismolab-reports", "reports": [{"station": "A"}]})
        self.assertFalse(c.import_reports(self.path("r2.json")).ok)
        self.assertFalse(c.import_insertions(self.path("r.json")).ok)

    def test_versions(self):
        c = make()
        c.create(1, "1.0", "10.0", "1.0", "1.0", T, "A")
        folder = os.path.join(self.tmp.name, "v")
        self.assertTrue(c.save_version("uno", folder).ok)
        self.assertFalse(c.save_version("uno", folder).ok)
        self.assertEqual([v["name"] for v in c.versions(folder)], ["uno"])
        c.delete(1)
        self.assertTrue(c.restore_version("uno", folder).ok)
        self.assertEqual(list(c.catalog.active), [1])
        self.assertFalse(c.restore_version("nada", folder).ok)


class ReadingTest(unittest.TestCase):
    def test_queries_audit_indicators_views(self):
        c = make()
        for i in range(1, 12):
            c.create(i, str(i / 2), "10.0", "300.0", "300.0", T, "A")
        c.review(11)
        self.assertEqual(len(c.query("top", k=3).data["results"]), 3)
        self.assertFalse(c.query("top", k=0).ok)
        self.assertFalse(c.query("top", k="x").ok)
        self.assertTrue(c.query("magnitude", low="1.0", high="3.0").ok)
        self.assertTrue(c.query("dates", depth="20", start=OLD, end=T).ok)
        self.assertIn("Referencia", c.query("associations", id=3).message)
        self.assertTrue(c.query("costly").ok)
        self.assertTrue(c.audit().ok)
        self.assertIn("Casos LL/RR/LR/RL", c.indicators_text())
        self.assertIn("Inorden", c.traversal_text())
        self.assertEqual(len(c.event_rows()), 11)
        self.assertEqual(len(c.history_rows()), 12)
        self.assertEqual(len(c.plane_view()["active"]), 11)
        self.assertEqual(len(c.tree_view()["layout"].nodes), 11)

    def test_priority_explanation_limits(self):
        c = make()
        c.create(1, "4.5", "31.0", "300.0", "300.0", T, "A")
        self.assertIn("H=31.0 > 30,0", explain_priority(c.catalog.active[1], ZONES))


if __name__ == "__main__":
    unittest.main()

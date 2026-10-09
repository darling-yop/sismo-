import unittest
from datetime import datetime, timezone

from domain.catalog import Catalog
from domain.models import Zone
from domain.reports import Report, process_report

T0 = "2026-09-07T10:00:00Z"


def rep(station="A", eid=1, rev=1, m=5.0, h=50.0, x=500.0, y=500.0, t=T0):
    return Report(station, eid, rev, m, h, x, y, t)


class ReportRulesTest(unittest.TestCase):
    def setUp(self):
        self.cat = Catalog(zones=[Zone("c", 0, 0, 100, 100, True)])

    def test_unknown_id_creates_event_even_with_revision_above_one(self):
        r = process_report(self.cat, rep(rev=3))
        self.assertEqual(r.decision, "alta")
        self.assertEqual(self.cat.active[1].revision, 3)
        self.assertEqual(self.cat.avl.size, 1)

    def test_higher_revision_replaces_data_and_moves_node(self):
        process_report(self.cat, rep(m=4.8, h=70.0))
        self.assertEqual(self.cat.active[1].priority, 2)
        r = process_report(self.cat, rep(station="B", rev=2, m=6.2, h=15.0))
        self.assertEqual(r.decision, "corregido")
        self.assertTrue(r.key_changed)
        event = self.cat.active[1]
        self.assertEqual((event.priority, event.revision), (3, 2))
        self.assertEqual(self.cat.avl.size, 1)
        self.assertEqual(self.cat.avl.inorder(), [event.key])
        self.assertEqual(event.stations, {"A", "B"})

    def test_old_revision_after_correction_changes_nothing(self):
        process_report(self.cat, rep(m=4.8, h=70.0))
        process_report(self.cat, rep(rev=2, m=6.2, h=15.0))
        r = process_report(self.cat, rep(station="C", rev=1, m=4.8, h=70.0))
        self.assertEqual(r.decision, "antiguo")
        self.assertEqual(self.cat.active[1].magnitude, 6.2)
        self.assertEqual(self.cat.avl.size, 1)
        self.assertNotIn("C", self.cat.active[1].stations)
        self.assertEqual(self.cat.counters["discarded"], 1)

    def test_confirmation_adds_station_once(self):
        process_report(self.cat, rep())
        r1 = process_report(self.cat, rep(station="B"))
        r2 = process_report(self.cat, rep(station="B"))
        self.assertEqual((r1.decision, r2.decision), ("confirmado", "confirmado"))
        self.assertEqual(self.cat.active[1].stations, {"A", "B"})
        self.assertEqual(self.cat.avl.size, 1)
        self.assertEqual(self.cat.counters["confirmations"], 2)

    def test_same_revision_different_data_is_conflict(self):
        process_report(self.cat, rep())
        r = process_report(self.cat, rep(station="B", m=5.1))
        self.assertEqual(r.decision, "conflicto")
        self.assertEqual(self.cat.active[1].magnitude, 5.0)
        self.assertEqual(self.cat.active[1].stations, {"A"})
        self.assertEqual(self.cat.counters["conflicts"], 1)

    def test_text_format_does_not_matter_for_equality(self):
        process_report(self.cat, rep(m=5.0))
        r = process_report(self.cat, rep(station="B", m="5.0", x="500", t=T0))
        self.assertEqual(r.decision, "confirmado")

    def test_deleted_id_is_rejected(self):
        process_report(self.cat, rep())
        self.cat.delete(1)
        r = process_report(self.cat, rep(rev=5))
        self.assertEqual(r.decision, "rechazado")
        self.assertNotIn(1, self.cat.active)

    def test_invalid_data_is_rejected_without_changes(self):
        r = process_report(self.cat, rep(m=11.0))
        self.assertEqual(r.decision, "invalido")
        self.assertEqual(self.cat.avl.size, 0)
        process_report(self.cat, rep())
        r = process_report(self.cat, rep(rev=2, m=5.55))
        self.assertEqual(r.decision, "invalido")
        self.assertEqual(self.cat.active[1].revision, 1)

    def test_invalid_revision_and_station(self):
        self.assertEqual(process_report(self.cat, rep(rev=0)).decision, "invalido")
        self.assertEqual(process_report(self.cat, rep(station="")).decision, "invalido")

    def test_archived_event_reactivated_only_by_higher_revision(self):
        process_report(self.cat, rep(m=1.0))
        self.cat.archived[1] = self.cat.active.pop(1)
        self.cat.avl.delete(self.cat.archived[1].key)
        self.assertEqual(process_report(self.cat, rep(station="B", m=1.0)).decision,
                         "confirmado")
        self.assertEqual(process_report(self.cat, rep(rev=0 + 1, station="C", m=1.0)).decision,
                         "confirmado")
        self.assertIn(1, self.cat.archived)
        self.assertEqual(self.cat.archived[1].stations, {"A", "B", "C"})
        r = process_report(self.cat, rep(rev=2, m=5.5))
        self.assertEqual(r.decision, "reactivado")
        self.assertIn(1, self.cat.active)
        self.assertNotIn(1, self.cat.archived)
        self.assertEqual(self.cat.active[1].attention, "pendiente")
        self.assertEqual(self.cat.avl.size, 1)

    def test_rotations_are_reported_per_step(self):
        total = 0
        for i in range(1, 8):  # ascending magnitudes -> RR rotations
            total += process_report(self.cat, rep(eid=i, m=float(i) * 0.1)).rotations
        self.assertGreater(total, 0)
        self.assertEqual(total, self.cat.avl.stats["left_rotations"]
                         + self.cat.avl.stats["right_rotations"])


if __name__ == "__main__":
    unittest.main()

import unittest

from domain.catalog import Catalog
from domain.models import PENDING, REVIEWED, ValidationError, Zone

ZONES = [Zone("Centro", 100.0, 100.0, 200.0, 200.0, True)]


def at(hh, mm=0):
    return f"2026-09-07T{hh:02d}:{mm:02d}:00Z"


def new_catalog():
    return Catalog(zones=ZONES, stations=["A", "B"])


class TestCreate(unittest.TestCase):
    def test_create_sets_revision_priority_and_inserts_in_avl(self):
        c = new_catalog()
        e = c.create("SIS-000010", 4.5, 30.0, 150.0, 150.0, at(10), "A")
        self.assertEqual((e.event_id, e.revision, e.priority), (10, 1, 3))
        self.assertEqual(e.attention, PENDING)
        self.assertEqual(e.stations, {"A"})
        self.assertEqual(c.avl.size, 1)
        self.assertEqual(c.avl.root.key, e.key)

    def test_invalid_data_changes_nothing(self):
        c = new_catalog()
        c.create(1, 5.0, 10.0, 150.0, 150.0, at(10), "A")
        bad = [
            (2, 10.1, 10.0, 1.0, 1.0, at(9), "A"),      # magnitude too high
            (2, 4.55, 10.0, 1.0, 1.0, at(9), "A"),      # two decimals
            (2, 4.5, -1.0, 1.0, 1.0, at(9), "A"),       # negative depth
            (2, 4.5, 10.0, 1000.1, 1.0, at(9), "A"),    # x out of range
            (2, 4.5, 10.0, 1.0, 1.0, "ayer", "A"),      # bad date
            (2, 4.5, 10.0, 1.0, 1.0, at(13), "A"),      # after the clock (12:00)
            (2, 4.5, 10.0, 1.0, 1.0, at(9), "Z"),       # unknown station
            (0, 4.5, 10.0, 1.0, 1.0, at(9), "A"),       # bad id
            (1, 4.5, 10.0, 1.0, 1.0, at(9), "A"),       # duplicate id
        ]
        for args in bad:
            with self.assertRaises(ValidationError, msg=str(args)):
                c.create(*args)
        self.assertEqual(c.avl.size, 1)
        self.assertEqual(list(c.active), [1])

    def test_deleted_and_archived_ids_cannot_be_reused(self):
        c = new_catalog()
        c.create(1, 5.0, 10.0, 150.0, 150.0, at(10), "A")
        c.delete(1)
        with self.assertRaises(ValidationError):
            c.create(1, 5.0, 10.0, 150.0, 150.0, at(10), "A")

    def test_tie_on_priority_and_magnitude_is_broken_by_id(self):
        c = new_catalog()
        for eid in (30, 10, 20):
            c.create(eid, 5.0, 100.0, 500.0, 500.0, at(10), "A")
        self.assertEqual([k.event_id for k in c.avl.inorder()], [10, 20, 30])


class TestCorrect(unittest.TestCase):
    def test_section16_correction_changes_priority_2_to_3(self):
        c = new_catalog()
        old = c.create(5, 4.8, 70.0, 150.0, 150.0, at(10), "A")
        old_key = old.key
        self.assertEqual(old.priority, 2)

        new = c.correct(5, magnitude=6.2, depth=15.0)
        self.assertEqual((new.priority, new.revision), (3, 2))
        self.assertEqual(c.avl.size, 1)                       # no second node
        self.assertIsNone(c.avl.find(old_key)[0])             # old key is gone
        self.assertIsNotNone(c.avl.find(new.key)[0])          # new key present
        self.assertEqual(new.attention, PENDING)

    def test_correction_with_same_key_still_bumps_revision(self):
        c = new_catalog()
        c.create(5, 4.8, 70.0, 500.0, 500.0, at(10), "A")
        new = c.correct(5, depth=80.0)
        self.assertEqual(new.revision, 2)
        self.assertEqual(c.avl.size, 1)

    def test_invalid_correction_changes_nothing(self):
        c = new_catalog()
        c.create(5, 4.8, 70.0, 150.0, 150.0, at(10), "A")
        with self.assertRaises(ValidationError):
            c.correct(5, magnitude=11.0)
        with self.assertRaises(ValidationError):
            c.correct(5, station="B")
        self.assertEqual(c.active[5].revision, 1)
        self.assertEqual(c.active[5].magnitude, 4.8)

    def test_correction_returns_event_to_pending(self):
        c = new_catalog()
        c.create(5, 4.8, 70.0, 150.0, 150.0, at(10), "A")
        self.assertEqual(c.mark_reviewed(5).attention, REVIEWED)
        self.assertEqual(c.correct(5, depth=71.0).attention, PENDING)

    def test_mark_reviewed_does_not_touch_the_tree(self):
        c = new_catalog()
        e = c.create(5, 4.8, 70.0, 150.0, 150.0, at(10), "A")
        c.mark_reviewed(5)
        self.assertEqual(c.active[5].key, e.key)
        self.assertEqual(c.active[5].revision, 1)


class TestDeleteAndLookup(unittest.TestCase):
    def test_delete_keeps_the_other_events_active(self):
        c = new_catalog()
        for eid, mag in ((1, 5.0), (2, 4.0), (3, 6.5), (4, 3.0), (5, 5.5)):
            c.create(eid, mag, 100.0, 500.0, 500.0, at(10), "A")
        c.delete(1)
        self.assertEqual(sorted(c.active), [2, 3, 4, 5])
        self.assertEqual(c.avl.size, 4)
        self.assertEqual(c.status_of(1), "eliminado")

    def test_lookup_reports_status_and_node_info(self):
        c = new_catalog()
        for eid, mag in ((1, 5.0), (2, 4.0), (3, 6.5)):
            c.create(eid, mag, 100.0, 500.0, 500.0, at(10), "A")
        info = c.lookup("SIS-000003")
        self.assertEqual(info["status"], "activo")
        self.assertEqual(info["visited"], info["node_depth"] + 1)
        self.assertIn(info["balance"], (-1, 0, 1))
        c.delete(3)
        self.assertEqual(c.lookup(3)["status"], "eliminado")
        self.assertEqual(c.lookup(99)["status"], None)


class TestClockAndParameters(unittest.TestCase):
    def test_clock_only_moves_forward(self):
        c = new_catalog()
        c.advance_clock(2)
        c.create(1, 5.0, 10.0, 1.0, 1.0, at(13), "A")  # now allowed
        with self.assertRaises(ValidationError):
            c.advance_clock(-1)

    def test_invalid_parameters_change_nothing(self):
        c = new_catalog()
        for kwargs in ({"W": 0}, {"R": -1}, {"L": -1}, {"L": 1.5}, {"T": 0}):
            with self.assertRaises(ValidationError):
                c.set_parameters(**kwargs)
        self.assertEqual((c.W, c.R, c.L, c.T), (48, 40, 3, 72))


if __name__ == "__main__":
    unittest.main()

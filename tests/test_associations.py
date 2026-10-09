import unittest
from datetime import datetime, timezone

from domain.associations import choose_reference, is_candidate
from domain.catalog import Catalog
from domain.models import Event


def at(hh, mm=0):
    return f"2026-09-07T{hh:02d}:{mm:02d}:00Z"


def ev(eid, mag, x, y, hh, mm=0):
    return Event(eid, mag, 10.0, x, y, datetime(2026, 9, 7, hh, mm, tzinfo=timezone.utc))


class TestCandidateRule(unittest.TestCase):
    def test_needs_greater_magnitude_and_strictly_earlier(self):
        a, b = ev(1, 5.0, 0, 0, 10), ev(2, 4.0, 0, 0, 11)
        self.assertTrue(is_candidate(a, b, 48, 40))
        self.assertFalse(is_candidate(b, a, 48, 40))                 # reversed
        self.assertFalse(is_candidate(ev(3, 5.0, 0, 0, 11), b, 48, 40))  # same time
        self.assertFalse(is_candidate(ev(3, 4.0, 0, 0, 10), b, 48, 40))  # same magnitude

    def test_radius_is_inclusive(self):
        b = ev(2, 4.0, 0.0, 0.0, 11)
        self.assertTrue(is_candidate(ev(1, 5.0, 24.0, 32.0, 10), b, 48, 40))    # 40.0
        self.assertFalse(is_candidate(ev(1, 5.0, 24.0, 32.1, 10), b, 48, 40))   # 40.0..

    def test_window_is_inclusive(self):
        b = ev(2, 4.0, 0, 0, 10)
        a_edge = Event(1, 5.0, 10.0, 0, 0, datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc))
        a_over = Event(3, 5.0, 10.0, 0, 0, datetime(2026, 9, 5, 9, 59, tzinfo=timezone.utc))
        self.assertTrue(is_candidate(a_edge, b, 48, 40))     # exactly 48 h
        self.assertFalse(is_candidate(a_over, b, 48, 40))    # 48 h and 1 min


class TestPolicy(unittest.TestCase):
    def test_highest_magnitude_then_latest_then_lowest_id(self):
        self.assertEqual(choose_reference([ev(1, 5.0, 0, 0, 9), ev(2, 6.0, 0, 0, 8)]).event_id, 2)
        self.assertEqual(choose_reference([ev(1, 5.0, 0, 0, 8), ev(2, 5.0, 0, 0, 9)]).event_id, 2)
        self.assertEqual(choose_reference([ev(7, 5.0, 0, 0, 9), ev(3, 5.0, 0, 0, 9)]).event_id, 3)
        self.assertIsNone(choose_reference([]))

    def test_order_of_arrival_does_not_matter(self):
        a, b = ev(1, 5.0, 0, 0, 9), ev(2, 6.0, 0, 0, 8)
        self.assertEqual(choose_reference([a, b]).event_id, choose_reference([b, a]).event_id)


class TestCatalogAssociations(unittest.TestCase):
    def late_report_catalog(self):
        c = Catalog()
        c.create(1, 5.6, 10.0, 500.0, 500.0, at(10, 0), "A")
        c.create(2, 4.2, 10.0, 505.0, 500.0, at(10, 20), "A")
        return c

    def test_section16_late_report(self):
        c = self.late_report_catalog()
        self.assertEqual(c.active[2].reference_id, 1)
        c.create(3, 6.1, 10.0, 502.0, 500.0, at(9, 55), "B")   # arrives late
        self.assertEqual({e.event_id for e in c.candidates_of(c.active[2])}, {1, 3})
        self.assertEqual(c.active[2].reference_id, 3)           # 6.1 beats 5.6
        self.assertEqual(c.active[1].reference_id, 3)
        self.assertIsNone(c.active[3].reference_id)
        self.assertEqual(c.used_as_reference_by(3), [1, 2])

    def test_delete_reference_updates_dependants(self):
        c = self.late_report_catalog()
        c.create(3, 6.1, 10.0, 502.0, 500.0, at(9, 55), "B")
        c.delete(3)
        self.assertEqual(c.active[2].reference_id, 1)
        self.assertIsNone(c.active[1].reference_id)

    def test_correction_updates_associations(self):
        c = self.late_report_catalog()
        c.correct(1, magnitude=3.0)           # no longer greater than 4.2
        self.assertIsNone(c.active[2].reference_id)

    def test_changing_w_or_r_recomputes(self):
        c = self.late_report_catalog()
        c.set_parameters(R=1)
        self.assertIsNone(c.active[2].reference_id)
        c.set_parameters(R=40)
        self.assertEqual(c.active[2].reference_id, 1)
        c.set_parameters(W=0.1)               # 6 minutes
        self.assertIsNone(c.active[2].reference_id)

    def test_archived_events_are_candidates_but_deleted_are_not(self):
        c = self.late_report_catalog()
        c.archived[1] = c.active.pop(1)       # simulate an archive
        c.avl.delete(c.archived[1].key)
        c.recompute_all_associations()
        self.assertEqual(c.active[2].reference_id, 1)
        c.deleted[1] = c.archived.pop(1)
        c.recompute_all_associations()
        self.assertIsNone(c.active[2].reference_id)

    def test_no_cycles_on_random_data(self):
        import random
        rng = random.Random(3)
        c = Catalog()
        for eid in range(1, 80):
            c.create(eid, round(rng.uniform(0, 8), 1), 10.0,
                     round(rng.uniform(0, 60), 1), round(rng.uniform(0, 60), 1),
                     at(rng.randint(0, 11), rng.randint(0, 59)), "A")
        for e in c.active.values():
            seen, current = set(), e
            while current is not None and current.reference_id is not None:
                self.assertNotIn(current.event_id, seen)
                seen.add(current.event_id)
                current = c.active.get(current.reference_id)


if __name__ == "__main__":
    unittest.main()

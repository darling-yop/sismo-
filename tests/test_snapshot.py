import json
import random
import unittest

from domain.reports import Report
from services.scenario import Scenario
from services.snapshot import capture, restore
from tests.helpers import is_valid_avl

CLOCK_TIME = "2026-09-01T00:00:00Z"


def populated(stress=False, n=40, seed=3):
    sc = Scenario()
    if stress:
        sc.set_stress(True)
    rnd = random.Random(seed)
    for i in range(1, n + 1):
        sc.create_event(i, round(rnd.uniform(0, 7), 1), 40.0, 10.0 * i % 1000,
                        5.0 * i % 1000, CLOCK_TIME, "A")
    return sc


class SnapshotTest(unittest.TestCase):
    def test_roundtrip_is_exact_for_normal_tree(self):
        sc = populated()
        data = capture(sc.catalog, sc.queue)
        cat, queue = restore(data)
        self.assertEqual(capture(cat, queue), data)
        self.assertEqual(cat.avl.preorder(), sc.catalog.avl.preorder())
        self.assertTrue(is_valid_avl(cat.avl))

    def test_stress_topology_survives_without_rebalancing(self):
        sc = Scenario()
        sc.set_stress(True)
        for i in range(1, 30):   # ascending keys: a degenerate chain
            sc.create_event(i, 1.0, 40.0, 1.0, 1.0, CLOCK_TIME, "A")
        self.assertEqual(sc.catalog.avl.height(), 28)
        data = capture(sc.catalog, sc.queue)
        cat, _ = restore(data)
        self.assertTrue(cat.avl.stress)
        self.assertEqual(cat.avl.height(), 28)
        self.assertEqual(cat.avl.preorder(), sc.catalog.avl.preorder())

    def test_snapshot_is_json_serializable_and_roundtrips(self):
        sc = populated()
        sc.enqueue_reports([Report("A", 99, 1, 5.0, 10.0, 1.0, 1.0, CLOCK_TIME)])
        data = capture(sc.catalog, sc.queue)
        again = json.loads(json.dumps(data))
        cat, queue = restore(again)
        self.assertEqual(capture(cat, queue), data)

    def test_photo_is_independent_from_live_objects(self):
        sc = populated(n=10)
        data = capture(sc.catalog, sc.queue)
        frozen = json.dumps(data, sort_keys=True)
        sc.correct_event(1, magnitude=9.0)
        sc.delete_event(2)
        sc.catalog.active[3].stations.add("Z")
        self.assertEqual(json.dumps(data, sort_keys=True), frozen)

    def test_counters_stats_queue_clock_params_are_kept(self):
        sc = populated(n=20)
        sc.advance_clock(5)
        sc.set_parameters(W=10, R=5.5, L=1, T=24)
        sc.enqueue_reports([Report("B", 1, 1, 1.0, 1.0, 1.0, 1.0, CLOCK_TIME),
                            Report("B", 2, 1, 1.0, 1.0, 1.0, 1.0, CLOCK_TIME)])
        sc.step()
        data = capture(sc.catalog, sc.queue)
        cat, queue = restore(data)
        self.assertEqual((cat.W, cat.R, cat.L, cat.T), (10, 5.5, 1, 24))
        self.assertEqual(cat.clock, sc.catalog.clock)
        self.assertEqual(cat.counters, sc.catalog.counters)
        self.assertEqual(cat.avl.stats, sc.catalog.avl.stats)
        self.assertEqual([r.event_id for r in queue.to_list()], [2])


if __name__ == "__main__":
    unittest.main()

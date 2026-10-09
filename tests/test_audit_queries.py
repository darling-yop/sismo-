import random
import unittest
from datetime import timedelta

from domain.audit import audit_catalog
from domain.comparison import compare, insertion_orders
from domain.metrics import indicators, traversals
from domain.models import ValidationError, Zone, parse_time
from domain.queries import (associations, by_magnitude, costly_access,
                            shallow_in_dates, top_pending)
from services.scenario import Scenario

T = "2026-09-07T10:00:00Z"


def random_scenario(n=60, seed=1, stress=False):
    sc = Scenario(zones=[Zone("c", 0, 0, 400, 400, True)])
    if stress:
        sc.catalog.avl.stress = True
    rnd = random.Random(seed)
    cat = sc.catalog                     # direct calls: no photo per event
    for i in range(1, n + 1):
        cat.create(i, round(rnd.uniform(-1, 8), 1), float(rnd.randint(0, 100)),
                   float(rnd.randint(0, 800)), float(rnd.randint(0, 800)),
                   f"2026-09-0{rnd.randint(1, 6)}T{rnd.randint(0, 23):02d}:00:00Z", "A")
    return sc


class AuditTest(unittest.TestCase):
    def test_clean_trees_pass_in_both_modes(self):
        sc = random_scenario()
        self.assertTrue(audit_catalog(sc.catalog)["balanced"])
        sc2 = random_scenario(stress=True)
        report = audit_catalog(sc2.catalog)
        self.assertTrue(report["ok"])                # imbalance is expected
        self.assertGreater(report["max_imbalance"], 1)
        self.assertFalse(report["balanced"])

    def test_normal_mode_imbalance_is_an_error(self):
        sc = random_scenario(stress=True)
        sc.catalog.avl.stress = False                # lie about the mode
        kinds = {e["kind"] for e in audit_catalog(sc.catalog)["errors"]}
        self.assertIn("balance", kinds)

    def test_global_order_violation_deep_in_the_tree(self):
        sc = random_scenario(40)
        avl = sc.catalog.avl
        node = avl.root
        while node.left is not None:                 # leftmost leaf
            node = node.left
        deep = node
        # make it bigger than the root while it is a valid child of its parent
        root_key = avl.root.key
        deep.key = type(root_key)(3, 9.9, 999999)
        report = audit_catalog(sc.catalog)
        self.assertFalse(report["ok"])
        self.assertIn(deep.key.event_id, report["by_event"])
        self.assertTrue(any(e["kind"] == "orden" for e in report["errors"]))

    def test_wrong_height_and_metadata_and_reference(self):
        sc = random_scenario(30)
        avl, cat = sc.catalog.avl, sc.catalog
        avl.root.height += 3
        victim = next(iter(cat.active.values()))
        victim.priority = 1 if victim.priority != 1 else 2
        other = list(cat.active.values())[5]
        other.reference_id = 424242
        kinds = {e["kind"] for e in audit_catalog(cat)["errors"]}
        self.assertTrue({"altura", "metadatos", "referencia"} <= kinds)

    def test_cycle_does_not_hang(self):
        sc = random_scenario(10)
        node = sc.catalog.avl.root
        while node.left is not None:
            node = node.left
        node.left = sc.catalog.avl.root              # cycle
        report = audit_catalog(sc.catalog)
        self.assertTrue(any(e["kind"] == "unicidad" for e in report["errors"]))


class QueryTest(unittest.TestCase):
    def test_top_pending_descending_skips_reviewed_and_stops_early(self):
        sc = random_scenario(80)
        cat = sc.catalog
        best = max(cat.active.values(), key=lambda e: e.key.as_tuple())
        cat.mark_reviewed(best.event_id)
        out = top_pending(cat, 5)
        expected = sorted((e for e in cat.active.values() if e.attention == "pendiente"),
                          key=lambda e: e.key.as_tuple(), reverse=True)[:5]
        self.assertEqual([e.event_id for e in out["results"]], [e.event_id for e in expected])
        self.assertNotIn(best.event_id, [e.event_id for e in out["results"]])
        self.assertLess(out["examined"], 80)
        self.assertEqual(len(top_pending(cat, 500)["results"]), 79)
        with self.assertRaises(ValidationError):
            top_pending(cat, 0)

    def test_magnitude_range_matches_bruteforce(self):
        for seed in range(12):
            sc = random_scenario(70, seed, stress=bool(seed % 2))
            rnd = random.Random(seed)
            low = round(rnd.uniform(-2, 6), 1)
            high = round(low + rnd.uniform(0, 3), 1)
            out = by_magnitude(sc.catalog, low, high)
            expected = sorted((e for e in sc.catalog.active.values()
                               if low <= e.magnitude <= high), key=lambda e: e.key.as_tuple())
            self.assertEqual([e.event_id for e in out["results"]],
                             [e.event_id for e in expected], seed)
        narrow = by_magnitude(random_scenario(300, 4).catalog, 4.0, 4.1)
        self.assertLess(narrow["examined"], 300)
        with self.assertRaises(ValidationError):
            by_magnitude(sc.catalog, 5.0, 4.0)

    def test_magnitude_bounds_are_inclusive(self):
        sc = Scenario()
        for i, m in enumerate((1.0, 1.5, 2.0, 2.5), start=1):
            sc.create_event(i, m, 70.0, 1.0, 1.0, T, "A")
        ids = [e.event_id for e in by_magnitude(sc.catalog, 1.5, 2.0)["results"]]
        self.assertEqual(ids, [2, 3])

    def test_shallow_in_dates_matches_bruteforce_and_scans_all(self):
        sc = random_scenario(90, 7)
        start, end = "2026-09-02T00:00:00Z", "2026-09-04T12:00:00Z"
        out = shallow_in_dates(sc.catalog, 40.0, start, end)
        t1, t2 = parse_time(start), parse_time(end)
        expected = [e.event_id for e in sorted(sc.catalog.active.values(),
                    key=lambda e: e.key.as_tuple())
                    if e.depth <= 40.0 and t1 <= e.time <= t2]
        self.assertEqual([e.event_id for e in out["results"]], expected)
        self.assertEqual(out["examined"], 90)
        with self.assertRaises(ValidationError):
            shallow_in_dates(sc.catalog, 40.0, end, start)

    def test_associations_with_active_archived_and_users(self):
        sc = Scenario()
        sc.create_event(1, 5.6, 70.0, 500.0, 500.0, "2026-09-07T10:00:00Z", "A")
        sc.create_event(2, 4.2, 70.0, 505.0, 500.0, "2026-09-07T10:20:00Z", "A")
        sc.create_event(3, 6.1, 70.0, 502.0, 500.0, "2026-09-07T09:55:00Z", "A")
        sc.catalog.archived[3] = sc.catalog.active.pop(3)     # archived reference
        sc.catalog.avl.delete(sc.catalog.archived[3].key)
        out = associations(sc.catalog, 2)
        self.assertEqual([(e.event_id, s) for e, s in out["candidates"]],
                         [(3, "archivado"), (1, "activo")])
        self.assertEqual((out["reference"][0].event_id, out["reference"][1]), (3, "archivado"))
        used = associations(sc.catalog, 3)
        self.assertEqual([e.event_id for e, _ in used["used_by"]], [1, 2])
        with self.assertRaises(ValidationError):
            associations(sc.catalog, 99)

    def test_deleted_event_has_no_associations(self):
        sc = Scenario()
        sc.create_event(1, 5.0, 70.0, 1.0, 1.0, T, "A")
        sc.delete_event(1)
        out = associations(sc.catalog, 1)
        self.assertEqual((out["status"], out["results"]), ("eliminado", []))

    def test_costly_access_matches_bruteforce_and_prunes(self):
        for seed in range(8):
            sc = random_scenario(120, seed, stress=True)
            cat = sc.catalog
            cat.L = seed % 4
            out = costly_access(cat)
            expected = sorted(((e.key.as_tuple(), cat.avl.find(e.key)[1] - 1)
                               for e in cat.active.values()
                               if e.priority == 3 and cat.avl.find(e.key)[1] - 1 > cat.L),
                              reverse=True)
            got = [(r["event"].key.as_tuple(), r["depth"]) for r in out["results"]]
            self.assertEqual(got, expected, seed)
            for row in out["results"]:
                self.assertEqual(row["visited"], row["depth"] + 1)
                self.assertEqual(row["limit"], cat.L)
        sc = Scenario()
        sc.catalog.avl.stress = True
        for i in range(1, 60):                       # low priority chain + one P3 at depth 59
            sc.catalog.create(i, 1.0, 70.0, 1.0, 1.0, T, "A")
        sc.catalog.create(100, 7.0, 70.0, 1.0, 1.0, T, "A")
        out = costly_access(sc.catalog)
        self.assertEqual(len(out["results"]), 1)
        self.assertLess(out["examined"], 61)

    def test_indicators_and_traversals(self):
        sc = random_scenario(50)
        cat = sc.catalog
        cat.mark_reviewed(1)
        data = indicators(cat, sc.queue)
        self.assertEqual(sum(data["by_priority"].values()), 50)
        self.assertEqual(data["pending"], 49)
        self.assertEqual(data["active"], 50)
        self.assertEqual(data["height"], cat.avl.height())
        orders = traversals(cat.avl)
        self.assertEqual(set(orders), {"inorder", "preorder", "postorder", "level_order"})
        self.assertTrue(all(len(v) == 50 for v in orders.values()))


class ComparisonTest(unittest.TestCase):
    def test_avl_vs_bst_on_ascending_order(self):
        sc = random_scenario(255, 2)
        keys = [e.key for e in sc.catalog.active.values()]
        out = {name: compare(order) for name, order in insertion_orders(keys).items()}
        self.assertEqual(out["ascending"]["bst"]["height"], 254)
        self.assertLessEqual(out["ascending"]["avl"]["height"], 11)
        self.assertLess(out["ascending"]["avl"]["search_comparisons"],
                        out["ascending"]["bst"]["search_comparisons"])
        self.assertEqual(out["ascending"]["avl"]["size"], 255)
        self.assertEqual(out["random"]["avl"]["leaves"] > 0, True)


if __name__ == "__main__":
    unittest.main()

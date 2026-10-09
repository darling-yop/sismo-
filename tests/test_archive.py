import random
import unittest
from datetime import timedelta

from domain.archive import plan_archive
from services.scenario import Scenario
from tests.helpers import is_valid_avl

OLD = "2026-09-01T00:00:00Z"      # default clock is 2026-09-07T12:00:00Z (>72 h)
RECENT = "2026-09-07T10:00:00Z"   # 2 h old


def add(sc, eid, mag, depth=70.0, when=OLD):
    sc.create_event(eid, mag, depth, 500.0 + eid % 5 * 100.0, 900.0, when, "A")


def build(spec, stress=True):
    sc = Scenario()
    if stress:
        sc.set_stress(True)
    for eid, mag, depth, when in spec:
        add(sc, eid, mag, depth, when)
    return sc


def reference_choice(sc):
    """Brute force, recursive, independent from plan_archive."""
    cat = sc.catalog
    best = []

    def walk(node, depth):
        if node is None:
            return 0, True
        ls, lok = walk(node.left, depth + 1)
        rs, rok = walk(node.right, depth + 1)
        e = cat.active[node.key.event_id]
        ok = (lok and rok and e.priority == 1
              and (cat.clock - e.time) > timedelta(hours=cat.T))
        size = ls + rs + 1
        if ok:
            best.append((size, depth, node.key.event_id))
        return size, ok

    walk(cat.avl.root, 0)
    return max(best) if best else None


class ArchiveTest(unittest.TestCase):
    def test_branch_with_high_priority_descendant_is_not_eligible(self):
        # root P1, right child P3 (descendant of higher priority)
        sc = build([(1, 2.0, 70.0, OLD), (99, 6.5, 70.0, OLD),
                    (2, 1.0, 70.0, OLD), (3, 0.5, 70.0, OLD), (4, 1.5, 70.0, OLD)])
        plan = sc.preview_archive()
        self.assertEqual(plan.root_id, 2)          # whole tree is NOT eligible
        self.assertEqual(plan.ids, [2, 3, 4])
        self.assertEqual(plan.count, 3)
        self.assertIn("mayor cantidad de nodos", plan.justification)

    def test_tie_by_size_and_depth_picks_highest_root_id(self):
        sc = build([(50, 4.5, 70.0, OLD),            # P2 root
                    (60, 2.0, 70.0, RECENT),         # recent P1: not eligible
                    (7, 1.0, 70.0, OLD), (8, 0.5, 70.0, OLD),
                    (9, 3.0, 70.0, OLD), (10, 3.5, 70.0, OLD)])
        plan = sc.preview_archive()
        self.assertEqual((plan.root_id, plan.ids), (9, [9, 10]))
        self.assertIn("mayor identificador", plan.justification)

    def test_no_eligible_branch_keeps_state(self):
        sc = build([(1, 2.0, 70.0, RECENT), (2, 1.0, 70.0, RECENT)])
        self.assertIsNone(sc.preview_archive())
        before = sc.snapshot()
        with self.assertRaises(Exception):
            sc.archive_branch()
        self.assertEqual(sc.snapshot(), before)

    def test_age_must_be_strictly_greater_than_t(self):
        sc = Scenario()
        # clock 2026-09-07T12:00Z; exactly 72 h old -> not eligible
        add(sc, 1, 1.0, when="2026-09-04T12:00:00Z")
        self.assertIsNone(sc.preview_archive())
        sc.advance_clock(1)
        self.assertEqual(sc.preview_archive().ids, [1])

    def test_whole_tree_can_be_archived_and_undone(self):
        sc = build([(i, 1.0, 70.0, OLD) for i in range(1, 8)], stress=False)
        before = sc.snapshot()
        plan = sc.archive_branch()
        self.assertEqual(plan.count, 7)
        self.assertEqual(sc.catalog.avl.size, 0)
        self.assertEqual(sorted(sc.catalog.archived), list(range(1, 8)))
        self.assertEqual(sc.catalog.counters["mass_archives"], 1)
        self.assertEqual(sc.catalog.counters["archived_events"], 7)
        sc.undo()
        self.assertEqual(sc.snapshot(), before)

    def test_archive_keeps_identity_data_and_associations(self):
        sc = Scenario()
        add(sc, 1, 5.0, depth=70.0, when="2026-08-30T00:00:00Z")  # old, P2
        sc.create_event(2, 1.0, 70.0, 610.0, 900.0, "2026-08-30T10:00:00Z", "A")
        ref = sc.catalog.active[2].reference_id
        self.assertEqual(ref, 1)
        sc.archive_branch()
        self.assertIn(2, sc.catalog.archived)
        self.assertEqual(sc.catalog.archived[2].reference_id, 1)
        self.assertEqual(sc.catalog.archived[2].magnitude, 1.0)

    def test_stress_mode_keeps_order_normal_mode_rebalances(self):
        rnd = random.Random(11)
        spec = [(i, round(rnd.uniform(0, 4.4), 1), 70.0,
                 OLD if rnd.random() < 0.7 else RECENT) for i in range(1, 121)]
        spec += [(500 + k, 6.5, 70.0, OLD) for k in range(3)]
        for stress in (True, False):
            sc = build(spec, stress)
            ids = sc.preview_archive().ids
            sc.archive_branch()
            keys = sc.catalog.avl.inorder()
            self.assertTrue(all(keys[i] < keys[i + 1] for i in range(len(keys) - 1)))
            self.assertEqual(sorted(sc.catalog.archived), ids)
            self.assertEqual(len(sc.catalog.active), sc.catalog.avl.size)
            if not stress:
                self.assertTrue(is_valid_avl(sc.catalog.avl))
                self.assertEqual(sc.catalog.avl.imbalanced_nodes(), [])

    def test_plan_matches_bruteforce_on_random_trees(self):
        for seed in range(25):
            rnd = random.Random(seed)
            spec = [(i, round(rnd.uniform(0, 5.0), 1), 70.0,
                     OLD if rnd.random() < 0.8 else RECENT)
                    for i in range(1, rnd.randint(2, 70))]
            sc = build(spec, stress=bool(seed % 2))
            expected = reference_choice(sc)
            plan = plan_archive(sc.catalog)
            if expected is None:
                self.assertIsNone(plan)
            else:
                size, depth, root_id = expected
                self.assertEqual((plan.count, plan.root_id), (size, root_id), seed)

    def test_deep_chain_does_not_hit_recursion_limit(self):
        sc = Scenario()
        sc.catalog.avl.stress = True        # build directly: no photo per event
        for i in range(1, 2001):
            sc.catalog.create(i, 1.0, 70.0, 500.0, 900.0, OLD, "A")
        self.assertEqual(sc.catalog.avl.height(), 1999)
        self.assertEqual(sc.preview_archive().count, 2000)
        sc.archive_branch()
        self.assertEqual(sc.catalog.avl.size, 0)

if __name__ == "__main__":
    unittest.main()

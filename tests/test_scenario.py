import random
import unittest

from domain.models import ValidationError, Zone
from domain.reports import Report
from services.history import History
from services.scenario import Scenario
from tests.helpers import is_valid_avl

T = "2026-09-07T10:00:00Z"


def make(n=25, seed=5):
    sc = Scenario(zones=[Zone("city", 0, 0, 300, 300, True)])
    rnd = random.Random(seed)
    for i in range(1, n + 1):
        sc.create_event(i, round(rnd.uniform(0, 7), 1), float(rnd.randint(0, 80)),
                        float(rnd.randint(0, 600)), float(rnd.randint(0, 600)),
                        T, "A")
    return sc


class UndoTest(unittest.TestCase):
    def assert_undo_restores(self, sc, action):
        before = sc.snapshot()
        depth = len(sc.history)
        action()
        self.assertEqual(len(sc.history), depth + 1, "one action = one entry")
        sc.undo()
        self.assertEqual(sc.snapshot(), before)
        self.assertEqual(len(sc.history), depth)

    def test_every_action_is_one_exact_undo(self):
        sc = make()
        self.assert_undo_restores(sc, lambda: sc.create_event(
            100, 6.5, 10.0, 10.0, 10.0, T, "B"))
        self.assert_undo_restores(sc, lambda: sc.correct_event(3, magnitude=6.9, depth=5.0))
        self.assert_undo_restores(sc, lambda: sc.mark_reviewed(4))
        self.assert_undo_restores(sc, lambda: sc.delete_event(5))
        self.assert_undo_restores(sc, lambda: sc.advance_clock(10))
        self.assert_undo_restores(sc, lambda: sc.set_parameters(W=5, R=3.0, L=0, T=10))
        self.assert_undo_restores(sc, lambda: sc.set_stress(True))
        self.assert_undo_restores(sc, lambda: sc.enqueue_reports(
            [Report("A", 200, 1, 5.0, 10.0, 1.0, 1.0, T)]))

    def test_failed_action_rolls_back_and_is_not_recorded(self):
        sc = make(5)
        before, depth = sc.snapshot(), len(sc.history)
        for bad in (lambda: sc.create_event(1, 5.0, 10.0, 1.0, 1.0, T, "A"),
                    lambda: sc.create_event(50, 99.0, 10.0, 1.0, 1.0, T, "A"),
                    lambda: sc.correct_event(1, magnitude=5.55),
                    lambda: sc.delete_event(77),
                    lambda: sc.advance_clock(-1)):
            with self.assertRaises(ValidationError):
                bad()
        self.assertEqual(sc.snapshot(), before)
        self.assertEqual(len(sc.history), depth)

    def test_undo_queue_step_restores_report_position_even_if_discarded(self):
        sc = Scenario()
        sc.create_event(1, 5.0, 70.0, 1.0, 1.0, T, "A")
        sc.correct_event(1, magnitude=5.5)            # revision 2
        sc.enqueue_reports([Report("B", 1, 1, 5.0, 70.0, 1.0, 1.0, T),   # old
                            Report("C", 9, 1, 3.0, 10.0, 2.0, 2.0, T)])  # new
        before = sc.snapshot()
        result = sc.step()
        self.assertEqual(result.decision, "antiguo")
        self.assertEqual(len(sc.queue), 1)
        self.assertEqual(sc.catalog.counters["discarded"], 1)
        sc.undo()
        self.assertEqual(sc.snapshot(), before)
        self.assertEqual([r.station for r in sc.queue.to_list()], ["B", "C"])
        self.assertEqual(sc.catalog.counters["discarded"], 0)

    def test_empty_queue_and_empty_history(self):
        sc = Scenario()
        with self.assertRaises(ValidationError):
            sc.step()
        with self.assertRaises(ValidationError):
            sc.undo()

    def test_successive_undo_returns_to_initial_state(self):
        sc = Scenario()
        initial = sc.snapshot()
        for i in range(1, 15):
            sc.create_event(i, 1.0 * (i % 6), 40.0, 5.0, 5.0, T, "A")
        sc.correct_event(2, magnitude=6.5)
        sc.delete_event(3)
        while len(sc.history):
            sc.undo()
        self.assertEqual(sc.snapshot(), initial)

    def test_history_limit_drops_oldest(self):
        history = History(limit=20)
        for i in range(200):
            history.push(f"a{i}", {})
        self.assertLessEqual(len(history), 20 + 10)
        self.assertEqual(history.entries()[-1][0], "a199")


class LogAndPauseTest(unittest.TestCase):
    def test_log_explains_metrics_of_each_action(self):
        sc = Scenario()
        sc.create_event(1, 4.8, 70.0, 1.0, 1.0, T, "A")
        sc.correct_event(1, magnitude=6.2, depth=15.0)
        sc.enqueue_reports([Report("B", 1, 1, 4.8, 70.0, 1.0, 1.0, T)])
        sc.step()
        log = sc.history.log()
        self.assertEqual(log[1]["metrics"], {"corrections": 1})
        self.assertEqual(log[3]["metrics"], {"discarded": 1, "reports_processed": 1})

    def test_rotations_appear_in_log(self):
        sc = Scenario()
        for i in (1, 2, 3):
            sc.create_event(i, 1.0, 70.0, 1.0, 1.0, T, "A")
        self.assertEqual(sc.history.log()[2]["metrics"],
                         {"RR": 1, "left_rotations": 1})

    def test_recovery_pauses_continuous_processing_until_resume(self):
        sc = Scenario()
        sc.set_stress(True)
        for i in range(1, 6):
            sc.create_event(i, 1.0, 70.0, 1.0, 1.0, T, "A")
        sc.enqueue_reports([Report("B", 9, 1, 1.0, 1.0, 1.0, 1.0, T)])
        sc.recover()
        with self.assertRaises(ValidationError):
            sc.step(continuous=True)
        sc.resume()
        self.assertEqual(sc.step(continuous=True).decision, "alta")


class StressRecoveryTest(unittest.TestCase):
    def test_four_cases_and_recovery_with_gap_over_two(self):
        sc = Scenario()
        sc.set_stress(True)
        for i in range(1, 41):                      # ascending: chain, gap 39
            sc.create_event(i, 1.0, 70.0, 1.0, 1.0, T, "A")
        avl = sc.catalog.avl
        self.assertEqual(avl.height(), 39)
        ids = sorted(sc.catalog.active)
        keys = avl.inorder()
        refs = {i: e.reference_id for i, e in sc.catalog.active.items()}
        self.assertEqual(sc.catalog.avl.stats["left_rotations"], 0)

        report = sc.recover()
        self.assertGreater(report["max_gap_before"], 2)
        self.assertEqual(report["imbalanced_after"], 0)
        self.assertFalse(avl.stress)
        self.assertTrue(is_valid_avl(sc.catalog.avl))
        self.assertEqual(sorted(sc.catalog.active), ids)
        self.assertEqual(sc.catalog.avl.inorder(), keys)
        self.assertEqual({i: e.reference_id for i, e in sc.catalog.active.items()}, refs)
        self.assertTrue(sc.paused)

    def test_undo_recovery_returns_exact_degraded_tree(self):
        sc = Scenario()
        sc.set_stress(True)
        for i in range(1, 16):
            sc.create_event(i, 1.0, 70.0, 1.0, 1.0, T, "A")
        before = sc.snapshot()
        sc.recover()
        sc.undo()
        self.assertEqual(sc.snapshot(), before)
        self.assertTrue(sc.catalog.avl.stress)
        self.assertEqual(sc.catalog.avl.height(), 14)

    def test_cannot_return_to_normal_while_unbalanced(self):
        sc = Scenario()
        sc.set_stress(True)
        for i in range(1, 6):
            sc.create_event(i, 1.0, 70.0, 1.0, 1.0, T, "A")
        with self.assertRaises(ValidationError):
            sc.set_stress(False)
        sc.recover()
        with self.assertRaises(ValidationError):
            sc.recover()                       # already normal

    def test_balanced_stress_tree_may_return_to_normal(self):
        sc = Scenario()
        sc.set_stress(True)
        for i in (2, 1, 3):
            sc.create_event(i, 1.0, 70.0, 1.0, 1.0, T, "A")
        sc.set_stress(False)
        self.assertFalse(sc.catalog.avl.stress)

    def test_all_four_rotation_cases_through_scenario(self):
        for order, case in (((3, 2, 1), "LL"), ((1, 2, 3), "RR"),
                            ((3, 1, 2), "LR"), ((1, 3, 2), "RL")):
            sc = Scenario()
            for i in order:
                sc.create_event(i, 1.0, 70.0, 1.0, 1.0, T, "A")
            self.assertEqual(sc.catalog.avl.stats[case], 1, case)
            self.assertTrue(is_valid_avl(sc.catalog.avl))


class LateReportCaseTest(unittest.TestCase):
    """Section 16: late report 5.6 at 10:00, 4.2 at 10:20, then 6.1 at 09:55."""

    def test_candidates_and_reference_policy(self):
        sc = Scenario()
        burst = [Report("A", 1, 1, 5.6, 70.0, 500.0, 500.0, "2026-09-07T10:00:00Z"),
                 Report("B", 2, 1, 4.2, 70.0, 505.0, 500.0, "2026-09-07T10:20:00Z"),
                 Report("C", 3, 1, 6.1, 70.0, 502.0, 500.0, "2026-09-07T09:55:00Z")]
        sc.enqueue_reports(burst)
        sc.step()
        sc.step()
        cat = sc.catalog
        self.assertEqual((cat.active[2].reference_id), 1)
        self.assertEqual(cat.active[1].reference_id, None)
        result = sc.step()
        self.assertEqual(result.decision, "alta")
        self.assertEqual(sorted(e.event_id for e in cat.candidates_of(cat.active[2])), [1, 3])
        self.assertEqual(cat.active[2].reference_id, 3)     # highest magnitude
        self.assertEqual(cat.active[1].reference_id, 3)
        self.assertEqual(cat.active[3].reference_id, None)
        self.assertEqual(len(cat.active), 3)
        sc.undo()                                           # undoes only step 3
        self.assertEqual(sorted(sc.catalog.active), [1, 2])
        self.assertEqual(sc.catalog.active[2].reference_id, 1)


class BurstTest(unittest.TestCase):
    def test_burst_with_all_decisions(self):
        sc = Scenario()
        base = ("2026-09-07T10:00:00Z")
        burst = [Report("A", 1, 1, 4.8, 70.0, 500.0, 500.0, base),      # alta
                 Report("B", 1, 1, 4.8, 70.0, 500.0, 500.0, base),      # confirm
                 Report("C", 1, 2, 6.2, 15.0, 500.0, 500.0, base),      # key changes
                 Report("D", 1, 1, 4.8, 70.0, 500.0, 500.0, base),      # old
                 Report("E", 1, 2, 6.3, 15.0, 500.0, 500.0, base)]      # conflict
        sc.enqueue_reports(burst)
        decisions = [sc.step().decision for _ in range(5)]
        self.assertEqual(decisions, ["alta", "confirmado", "corregido", "antiguo",
                                     "conflicto"])
        self.assertEqual(sc.catalog.avl.size, 1)
        self.assertEqual(sc.catalog.active[1].priority, 3)
        self.assertEqual(sc.catalog.active[1].magnitude, 6.2)
        self.assertEqual(len(sc.queue), 0)
        c = sc.catalog.counters
        self.assertEqual((c["confirmations"], c["corrections"], c["discarded"],
                          c["conflicts"], c["reports_processed"]), (1, 1, 1, 1, 5))


if __name__ == "__main__":
    unittest.main()

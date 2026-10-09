import random
import unittest

from core.avl import AVL
from core.bst import BST
from tests.helpers import check_tree, is_valid_avl


def build(values, stress=False):
    tree = AVL()
    tree.stress = stress
    for value in values:
        tree.insert(value)
    return tree


class TestRotationCases(unittest.TestCase):
    def check_case(self, values, name):
        tree = build(values)
        self.assertEqual(tree.root.key, 2)
        self.assertEqual(tree.preorder(), [2, 1, 3])
        self.assertEqual(tree.stats[name], 1)
        self.assertTrue(is_valid_avl(tree))
        return tree

    def test_ll(self):
        tree = self.check_case([3, 2, 1], "LL")
        self.assertEqual(tree.stats["right_rotations"], 1)

    def test_rr(self):
        tree = self.check_case([1, 2, 3], "RR")
        self.assertEqual(tree.stats["left_rotations"], 1)

    def test_lr_counts_one_case_and_two_rotations(self):
        tree = self.check_case([3, 1, 2], "LR")
        self.assertEqual(tree.stats["left_rotations"] + tree.stats["right_rotations"], 2)

    def test_rl_counts_one_case_and_two_rotations(self):
        tree = self.check_case([1, 3, 2], "RL")
        self.assertEqual(tree.stats["left_rotations"] + tree.stats["right_rotations"], 2)


class TestNormalMode(unittest.TestCase):
    def test_ascending_16_avl_height_4_vs_bst_height_15(self):
        avl, bst = AVL(), BST()
        for value in range(1, 17):
            avl.insert(value)
            bst.insert(value)
        self.assertEqual(avl.height(), 4)
        self.assertEqual(bst.height(), 15)
        self.assertTrue(is_valid_avl(avl))

    def test_random_inserts_and_deletes_stay_valid(self):
        rng = random.Random(1)
        tree, model = AVL(), set()
        for _ in range(1500):
            value = rng.randint(0, 300)
            if value in model and rng.random() < 0.6:
                self.assertTrue(tree.delete(value))
                model.remove(value)
            else:
                inserted = tree.insert(value) is not None
                self.assertEqual(inserted, value not in model)
                model.add(value)
            self.assertTrue(is_valid_avl(tree))
        self.assertEqual(tree.inorder(), sorted(model))

    def test_delete_does_not_remove_descendants(self):
        tree = build([50, 30, 70, 20, 40, 60, 80])
        tree.delete(50)
        self.assertEqual(tree.inorder(), [20, 30, 40, 60, 70, 80])


class TestStressAndRecovery(unittest.TestCase):
    def test_stress_keeps_order_but_not_balance(self):
        tree = build(range(100), stress=True)
        heights_ok, max_balance, ordered, size_ok = check_tree(tree)
        self.assertTrue(heights_ok and ordered and size_ok)
        self.assertEqual(tree.height(), 99)
        self.assertGreater(max_balance, 1)
        self.assertEqual(tree.stats["LL"] + tree.stats["RR"], 0)

    def test_recovery_with_gaps_larger_than_two(self):
        tree = build(range(500), stress=True)
        report = tree.recover()
        self.assertGreater(report["max_gap_before"], 2)
        self.assertEqual(report["imbalanced_after"], 0)
        self.assertTrue(is_valid_avl(tree))
        self.assertEqual(tree.inorder(), list(range(500)))
        self.assertGreater(report["rotations"], 0)

    def test_recovery_on_random_stress_trees(self):
        rng = random.Random(7)
        for trial in range(300):
            tree = AVL()
            tree.stress = True
            model = set()
            for _ in range(rng.randint(1, 150)):
                value = rng.randint(0, 200)
                if value in model and rng.random() < 0.4:
                    tree.delete(value)
                    model.remove(value)
                else:
                    tree.insert(value)
                    model.add(value)
            tree.recover()
            self.assertTrue(is_valid_avl(tree), f"trial {trial}")
            self.assertEqual(tree.inorder(), sorted(model))

    def test_recovery_covers_rotation_cases(self):
        tree = build(range(1, 11), stress=True)
        tree.recover()
        self.assertTrue(is_valid_avl(tree))
        self.assertGreater(tree.stats["RR"], 0)


if __name__ == "__main__":
    unittest.main()
import unittest

from core.bst import BST
from core.tree_key import TreeKey
from tests.helpers import check_tree


def build(values):
    tree = BST()
    for value in values:
        tree.insert(value)
    return tree


class TestBST(unittest.TestCase):
    def test_traversals(self):
        tree = build([8, 3, 10, 1, 6, 14, 4, 7, 13])
        self.assertEqual(tree.inorder(), [1, 3, 4, 6, 7, 8, 10, 13, 14])
        self.assertEqual(tree.preorder(), [8, 3, 1, 6, 4, 7, 10, 14, 13])
        self.assertEqual(tree.postorder(), [1, 4, 7, 6, 3, 13, 14, 10, 8])
        self.assertEqual(tree.level_order(), [8, 3, 10, 1, 6, 14, 4, 7, 13])

    def test_duplicate_rejected(self):
        tree = build([5, 3])
        self.assertIsNone(tree.insert(5))
        self.assertEqual(tree.size, 2)

    def test_find_counts_visited_nodes(self):
        tree = build([8, 3, 10, 1, 6])
        node, visited = tree.find(6)
        self.assertEqual(node.key, 6)
        self.assertEqual(visited, 3)
        node, visited = tree.find(99)
        self.assertIsNone(node)
        self.assertEqual(visited, 2)

    def test_delete_leaf_one_child_two_children_and_root(self):
        tree = build([8, 3, 10, 1, 6, 14, 4, 7, 13])
        self.assertTrue(tree.delete(1))
        self.assertTrue(tree.delete(14))
        self.assertTrue(tree.delete(3))
        self.assertTrue(tree.delete(8))
        self.assertFalse(tree.delete(99))
        self.assertEqual(tree.inorder(), [4, 6, 7, 10, 13])
        heights_ok, _, ordered, size_ok = check_tree(tree)
        self.assertTrue(heights_ok and ordered and size_ok)

    def test_delete_keeps_other_nodes(self):
        tree = build([50, 30, 70, 20, 40])
        tree.delete(30)
        self.assertEqual(tree.inorder(), [20, 40, 50, 70])

    def test_ascending_order_does_not_recurse(self):
        tree = build(range(3000))
        self.assertEqual(tree.height(), 2999)
        self.assertEqual(tree.leaf_count(), 1)
        self.assertEqual(len(tree.inorder()), 3000)

    def test_works_with_tree_keys(self):
        tree = BST()
        keys = [TreeKey(3, 5.2, 10), TreeKey(2, 5.8, 20), TreeKey(3, 6.1, 30)]
        for key in keys:
            tree.insert(key)
        self.assertEqual(tree.root.left.key, keys[1])
        self.assertEqual(tree.root.right.key, keys[2])


if __name__ == "__main__":
    unittest.main()
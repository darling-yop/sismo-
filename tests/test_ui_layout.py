import unittest

from core.avl import AVL
from core.bst import BST
from core.tree_key import TreeKey
from ui.layout import layout_tree


def keys(n):
    return [TreeKey(1, float(i % 40) / 10, i) for i in range(1, n + 1)]


class LayoutTest(unittest.TestCase):
    def test_empty(self):
        lay = layout_tree(AVL())
        self.assertEqual((lay.total, lay.columns, lay.root), (0, 0, None))

    def test_columns_follow_inorder_and_depth_follows_tree(self):
        tree = AVL()
        for k in keys(15):
            tree.insert(k)
        lay = layout_tree(tree)
        by_col = sorted(lay.nodes.values(), key=lambda n: n.column)
        self.assertEqual([n.key for n in by_col], [k.as_tuple() for k in tree.inorder()])
        self.assertEqual(lay.hidden, 0)
        self.assertEqual(lay.levels, tree.height() + 1)
        root = lay.nodes[lay.root]
        self.assertEqual(root.depth, 0)

    def test_chain_is_truncated_without_recursion(self):
        bst = BST()
        for k in sorted(keys(3000)):              # worst case: a 3000-level chain
            bst.insert(k)
        lay = layout_tree(bst, max_depth=5)
        self.assertEqual(len(lay.nodes), 6)
        self.assertEqual(lay.hidden, 3000 - 6)
        deepest = max(lay.nodes.values(), key=lambda n: n.depth)
        self.assertEqual(deepest.hidden_below, 3000 - 6)

    def test_children_links(self):
        tree = AVL()
        for k in keys(7):
            tree.insert(k)
        lay = layout_tree(tree)
        for node in lay.nodes.values():
            for child in (node.left, node.right):
                if child is not None:
                    self.assertEqual(lay.nodes[child].depth, node.depth + 1)


if __name__ == "__main__":
    unittest.main()

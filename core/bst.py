"""Plain BST with no balancing, used as a comparison to the AVL."""

from core.binary_tree import BinaryTree


class BST(BinaryTree):
    def _fix_path(self, path):
        for node in reversed(path):
            self.update_height(node)


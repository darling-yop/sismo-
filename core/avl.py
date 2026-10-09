"""AVL tree with normal mode, stress mode, and global recovery."""

from core.binary_tree import BinaryTree
from core.stack import Stack


class AVL(BinaryTree):
    def __init__(self):
        super().__init__()
        self.stress = False
        self.stats = {
            "LL": 0, "RR": 0, "LR": 0, "RL": 0,
            "left_rotations": 0, "right_rotations": 0,
        }

    def _rotate_right(self, node):
        pivot = node.left
        node.left = pivot.right
        pivot.right = node
        self.update_height(node)
        self.update_height(pivot)
        self.stats["right_rotations"] += 1
        return pivot

    def _rotate_left(self, node):
        pivot = node.right
        node.right = pivot.left
        pivot.left = node
        self.update_height(node)
        self.update_height(pivot)
        self.stats["left_rotations"] += 1
        return pivot

    def _rebalance(self, node):
        """Return a balanced subtree root, including when gaps exceed two."""
        if node is None:
            return None
        self.update_height(node)
        balance = self.balance_factor(node)
        while balance > 1 or balance < -1:
            if balance > 1:
                if self.balance_factor(node.left) < 0:
                    self.stats["LR"] += 1
                    node.left = self._rotate_left(node.left)
                else:
                    self.stats["LL"] += 1
                node = self._rotate_right(node)
            else:
                if self.balance_factor(node.right) > 0:
                    self.stats["RL"] += 1
                    node.right = self._rotate_right(node.right)
                else:
                    self.stats["RR"] += 1
                node = self._rotate_left(node)
            node.left = self._rebalance(node.left)
            node.right = self._rebalance(node.right)
            self.update_height(node)
            balance = self.balance_factor(node)
        return node

    def _fix_path(self, path):
        for index in range(len(path) - 1, -1, -1):
            node = path[index]
            if self.stress:
                self.update_height(node)
            else:
                new_root = self._rebalance(node)
                if new_root is not node:
                    parent = path[index - 1] if index > 0 else None
                    self._replace_child(parent, node, new_root)

    def imbalanced_nodes(self):
        """Return (key, balance factor) pairs for imbalanced nodes."""
        result, stack = [], Stack()
        if self.root is not None:
            stack.push(self.root)
        while not stack.is_empty():
            node = stack.pop()
            balance = self.balance_factor(node)
            if balance > 1 or balance < -1:
                result.append((node.key, balance))
            if node.left is not None:
                stack.push(node.left)
            if node.right is not None:
                stack.push(node.right)
        return result

    def recover(self):
        """Restore AVL balance bottom-up using rotations and return a report."""
        before = self.imbalanced_nodes()
        rotations_before = self.stats["left_rotations"] + self.stats["right_rotations"]
        cases_before = dict(self.stats)

        order, stack = [], Stack()
        if self.root is not None:
            stack.push((self.root, None))
        while not stack.is_empty():
            node, parent = stack.pop()
            order.append((node, parent))
            if node.left is not None:
                stack.push((node.left, node))
            if node.right is not None:
                stack.push((node.right, node))

        for node, parent in reversed(order):
            new_root = self._rebalance(node)
            if new_root is not node:
                self._replace_child(parent, node, new_root)

        rotations_after = self.stats["left_rotations"] + self.stats["right_rotations"]
        return {
            "imbalanced_before": len(before),
            "max_gap_before": max((abs(balance) for _, balance in before), default=0),
            "rotations": rotations_after - rotations_before,
            "cases": {key: self.stats[key] - cases_before[key]
                      for key in ("LL", "RR", "LR", "RL")},
            "imbalanced_after": len(self.imbalanced_nodes()),
            "height_after": self.height(),
            }


"""Logic shared by the BST and the AVL.

Everything is iterative on purpose: an unbalanced tree can be thousands of
levels deep and would hit Python's recursion limit.
"""

from core.fifo import Queue
from core.node import Node
from core.stack import Stack


def height_of(node):
    """Height of an empty tree is -1 and of a leaf is 0."""
    return node.height if node is not None else -1


class BinaryTree:
    def __init__(self):
        self.root = None
        self.size = 0

    @staticmethod
    def update_height(node):
        node.height = 1 + max(height_of(node.left), height_of(node.right))

    @staticmethod
    def balance_factor(node):
        """Left height minus right height."""
        return height_of(node.left) - height_of(node.right)

    def _replace_child(self, parent, old, new):
        """Make new take the place of old under parent (None means root)."""
        if parent is None:
            self.root = new
        elif parent.left is old:
            parent.left = new
        else:
            parent.right = new

    def _fix_path(self, path):
        """Update or rebalance ancestors after an insert or delete."""
        raise NotImplementedError

    def insert(self, key):
        """Insert key; return its node, or None when it already exists."""
        path = []
        current = self.root
        while current is not None:
            if key == current.key:
                return None
            path.append(current)
            current = current.left if key < current.key else current.right
        node = Node(key)
        if not path:
            self.root = node
        elif key < path[-1].key:
            path[-1].left = node
        else:
            path[-1].right = node
        self.size += 1
        self._fix_path(path)
        return node

    def find(self, key):
        """Return (node or None, nodes visited)."""
        visited = 0
        current = self.root
        while current is not None:
            visited += 1
            if key == current.key:
                return current, visited
            current = current.left if key < current.key else current.right
        return None, visited

    def delete(self, key):
        """Delete a key, replacing a two-child node with its predecessor."""
        path = []
        current = self.root
        while current is not None and key != current.key:
            path.append(current)
            current = current.left if key < current.key else current.right
        if current is None:
            return False

        if current.left is not None and current.right is not None:
            path.append(current)
            target = current.left
            while target.right is not None:
                path.append(target)
                target = target.right
            current.key = target.key
        else:
            target = current

        child = target.left if target.left is not None else target.right
        self._replace_child(path[-1] if path else None, target, child)
        self.size -= 1
        self._fix_path(path)
        return True

    def remove_subtree(self, key):
        """Detach the subtree rooted at key and return the number of nodes."""
        path = []
        current = self.root
        while current is not None and key != current.key:
            path.append(current)
            current = current.left if key < current.key else current.right
        if current is None:
            return 0

        count, stack = 0, Stack()
        stack.push(current)
        while not stack.is_empty():
            node = stack.pop()
            count += 1
            if node.left is not None:
                stack.push(node.left)
            if node.right is not None:
                stack.push(node.right)
        self._replace_child(path[-1] if path else None, current, None)
        self.size -= count
        self._fix_path(path)
        return count

    def inorder(self):
        return [node.key for node in self.nodes()]

    def nodes(self):
        """Return nodes in inorder (ascending keys)."""
        result, stack, current = [], Stack(), self.root
        while current is not None or not stack.is_empty():
            while current is not None:
                stack.push(current)
                current = current.left
            current = stack.pop()
            result.append(current)
            current = current.right
        return result

    def preorder(self):
        result, stack = [], Stack()
        if self.root is not None:
            stack.push(self.root)
        while not stack.is_empty():
            node = stack.pop()
            result.append(node.key)
            if node.right is not None:
                stack.push(node.right)
            if node.left is not None:
                stack.push(node.left)
        return result

    def postorder(self):
        result, stack = [], Stack()
        if self.root is not None:
            stack.push(self.root)
        while not stack.is_empty():
            node = stack.pop()
            result.append(node.key)
            if node.left is not None:
                stack.push(node.left)
            if node.right is not None:
                stack.push(node.right)
        result.reverse()
        return result

    def level_order(self):
        result, queue = [], Queue()
        if self.root is not None:
            queue.enqueue(self.root)
        while not queue.is_empty():
            node = queue.dequeue()
            result.append(node.key)
            if node.left is not None:
                queue.enqueue(node.left)
            if node.right is not None:
                queue.enqueue(node.right)
        return result

    def height(self):
        return height_of(self.root)

    def leaf_count(self):
        count, stack = 0, Stack()
        if self.root is not None:
            stack.push(self.root)
        while not stack.is_empty():
            node = stack.pop()
            if node.left is None and node.right is None:
                count += 1
            if node.left is not None:
                stack.push(node.left)
            if node.right is not None:
                stack.push(node.right)
        return count



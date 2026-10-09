"""LIFO stack (used for undo and for iterative tree traversals)."""


class Stack:
    """Backed by a Python list: push and pop are O(1) amortized, memory O(n)."""

    def __init__(self):
        self._items = []

    def push(self, item):
        self._items.append(item)

    def pop(self):
        if not self._items:
            raise IndexError("pop from empty stack")
        return self._items.pop()

    def peek(self):
        if not self._items:
            raise IndexError("peek from empty stack")
        return self._items[-1]

    def is_empty(self):
        return not self._items

    def __len__(self):
        return len(self._items)

    def to_list(self):
        """Items from bottom to top."""
        return list(self._items)
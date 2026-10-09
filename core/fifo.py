"""FIFO queue (used for pending reports and for level-order traversal)."""


class _Cell:
    __slots__ = ("value", "next")

    def __init__(self, value):
        self.value = value
        self.next = None


class Queue:
    """Singly linked list with head and tail pointers."""

    def __init__(self):
        self._head = None
        self._tail = None
        self._size = 0

    def enqueue(self, value):
        cell = _Cell(value)
        if self._tail is None:
            self._head = cell
        else:
            self._tail.next = cell
        self._tail = cell
        self._size += 1

    def dequeue(self):
        if self._head is None:
            raise IndexError("dequeue from empty queue")
        cell = self._head
        self._head = cell.next
        if self._head is None:
            self._tail = None
        self._size -= 1
        return cell.value

    def peek(self):
        if self._head is None:
            raise IndexError("peek at empty queue")
        return self._head.value

    def is_empty(self):
        return self._size == 0

    def __len__(self):
        return self._size

    def to_list(self):
        """Items in reception order (front first)."""
        items, cell = [], self._head
        while cell is not None:
            items.append(cell.value)
            cell = cell.next
        return items

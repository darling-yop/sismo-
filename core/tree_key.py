"""TreeKey: the ordered key K = (P, M, I) used by the AVL and the BST.

Tuple ordering compares priority first, then magnitude, then identifier.
"""


class TreeKey:
    __slots__ = ("priority", "magnitude", "event_id")

    def __init__(self, priority, magnitude, event_id):
        self.priority = priority
        self.magnitude = magnitude
        self.event_id = event_id

    def as_tuple(self):
        return (self.priority, self.magnitude, self.event_id)

    def __lt__(self, other):
        return self.as_tuple() < other.as_tuple()

    def __gt__(self, other):
        return self.as_tuple() > other.as_tuple()

    def __eq__(self, other):
        return isinstance(other, TreeKey) and self.as_tuple() == other.as_tuple()

    def __hash__(self):
        return hash(self.as_tuple())

    def __repr__(self):
        return f"TreeKey{self.as_tuple()}"
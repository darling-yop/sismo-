"""Tree node. It stores only the key and the links, never the event data.

Event data lives in a dict indexed by id, so rotations never touch it.
"""


class Node:
    def __init__(self, key):
        self.key = key
        self.left = None
        self.right = None
        self.height = 0  # a leaf has height 0 (empty tree is -1)

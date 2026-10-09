"""Tree layout: pure geometry, no Tkinter (so it can be unit tested).

x = position in the inorder sequence, y = node depth. This guarantees that
no two nodes overlap and that left/right order matches key order.
Everything is iterative: a degenerate BST can have thousands of levels.
"""

from dataclasses import dataclass, field

DEFAULT_MAX_DEPTH = 12     # deeper levels are summarized, not drawn


@dataclass
class DrawNode:
    event_id: int
    key: tuple
    column: int            # inorder index among the drawn nodes
    depth: int
    height: int
    balance: int
    left: int | None       # id of the drawn left child
    right: int | None
    hidden_below: int = 0  # nodes under this one that are not drawn


@dataclass
class TreeLayout:
    nodes: dict = field(default_factory=dict)    # id -> DrawNode
    columns: int = 0
    levels: int = 0
    total: int = 0
    hidden: int = 0
    root: int | None = None


def _balance(node):
    hl = node.left.height if node.left is not None else -1
    hr = node.right.height if node.right is not None else -1
    return hl - hr


def layout_tree(tree, max_depth=DEFAULT_MAX_DEPTH):
    """Layout of `tree` (AVL or BST) showing levels 0..max_depth."""
    result = TreeLayout(total=tree.size)
    if tree.root is None:
        return result
    result.root = tree.root.key.event_id

    # inorder traversal that stops at max_depth (iterative)
    stack, current, depth_of, column = [], tree.root, {id(tree.root): 0}, 0
    cols, order = {}, []
    while current is not None or stack:
        while current is not None:
            stack.append(current)
            depth = depth_of[id(current)]
            if depth < max_depth and current.left is not None:
                depth_of[id(current.left)] = depth + 1
                current = current.left
            else:
                current = None
        node = stack.pop()
        cols[id(node)] = column
        column += 1
        order.append(node)
        depth = depth_of[id(node)]
        if depth < max_depth and node.right is not None:
            depth_of[id(node.right)] = depth + 1
            current = node.right

    drawn = {id(n) for n in order}

    def count_below(node):          # subtree size minus drawn part, iterative
        total, todo = 0, [node]
        while todo:
            item = todo.pop()
            for child in (item.left, item.right):
                if child is not None and id(child) not in drawn:
                    total += 1
                    todo.append(child)
        return total

    for node in order:
        left = node.left.key.event_id if node.left is not None and id(node.left) in drawn else None
        right = node.right.key.event_id if node.right is not None and id(node.right) in drawn else None
        hidden = 0
        if (node.left is not None and left is None) or (node.right is not None and right is None):
            hidden = 0
            for child in (node.left, node.right):
                if child is not None and id(child) not in drawn:
                    hidden += 1 + count_below(child)
        eid = node.key.event_id
        result.nodes[eid] = DrawNode(eid, node.key.as_tuple(), cols[id(node)],
                                     depth_of[id(node)], node.height, _balance(node),
                                     left, right, hidden)
        result.levels = max(result.levels, depth_of[id(node)] + 1)
    result.columns = column
    result.hidden = result.total - len(order)
    return result

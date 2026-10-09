"""Independent tree checker for stored heights, ordering, and size."""


def check_tree(tree):
    """Return (heights_ok, max_abs_balance, ordered, size_ok)."""
    if tree.root is None:
        return True, 0, True, tree.size == 0

    order, stack = [], [tree.root]
    while stack:
        node = stack.pop()
        order.append(node)
        for child in (node.left, node.right):
            if child is not None:
                stack.append(child)

    real_heights = {}
    heights_ok, max_balance = True, 0
    for node in reversed(order):
        left_height = real_heights[id(node.left)] if node.left is not None else -1
        right_height = real_heights[id(node.right)] if node.right is not None else -1
        real_heights[id(node)] = 1 + max(left_height, right_height)
        max_balance = max(max_balance, abs(left_height - right_height))
        if node.height != real_heights[id(node)]:
            heights_ok = False

    keys = tree.inorder()
    ordered = all(keys[index] < keys[index + 1] for index in range(len(keys) - 1))
    return heights_ok, max_balance, ordered, len(order) == tree.size == len(keys)


def is_valid_avl(tree):
    heights_ok, max_balance, ordered, size_ok = check_tree(tree)
    return heights_ok and max_balance <= 1 and ordered and size_ok
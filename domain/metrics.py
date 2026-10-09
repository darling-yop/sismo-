"""Accumulated counters included in snapshots and undo state."""

COUNTER_NAMES = (
    "corrections",
    "confirmations",
    "conflicts",
    "discarded",
    "mass_archives",
    "archived_events",
    "reports_processed",
)


def new_counters():
    return {name: 0 for name in COUNTER_NAMES}


def node_depths(avl):
    """Return each event id's depth, with the root at depth zero."""
    depths, stack = {}, [(avl.root, 0)] if avl.root is not None else []
    while stack:
        node, depth = stack.pop()
        depths[node.key.event_id] = depth
        for child in (node.left, node.right):
            if child is not None:
                stack.append((child, depth + 1))
    return depths


def traversals(avl):
    """Return the four traversals as lists of key tuples."""
    return {"inorder": [key.as_tuple() for key in avl.inorder()],
            "preorder": [key.as_tuple() for key in avl.preorder()],
            "postorder": [key.as_tuple() for key in avl.postorder()],
            "level_order": [key.as_tuple() for key in avl.level_order()]}


def indicators(catalog, queue=None):
    from domain.queries import costly_access

    by_priority = {1: 0, 2: 0, 3: 0}
    pending = 0
    for event in catalog.active.values():
        by_priority[event.priority] += 1
        pending += event.attention == "pendiente"
    return {
        "mode": "estrés" if catalog.avl.stress else "normal",
        "active": len(catalog.active), "archived": len(catalog.archived),
        "deleted": len(catalog.deleted),
        "height": catalog.avl.height(), "leaves": catalog.avl.leaf_count(),
        "by_priority": by_priority, "pending": pending,
        "costly_access": len(costly_access(catalog)["results"]),
        "queue": len(queue) if queue is not None else 0,
        "counters": dict(catalog.counters),
        "rotations": dict(catalog.avl.stats),
    }
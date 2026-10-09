"""Independent AVL structure checks; stored heights are never trusted."""


def check_avl(tree):
    """Return height, ordering, size, and balance audit results."""
    if tree.root is None:
        return {"heights_ok": True, "max_imbalance": 0, "ordered": True,
                "size_ok": tree.size == 0, "balanced": tree.size == 0}
    order, stack = [], [tree.root]
    while stack:
        node = stack.pop()
        order.append(node)
        for child in (node.left, node.right):
            if child is not None:
                stack.append(child)
    real_heights, heights_ok, max_gap = {}, True, 0
    for node in reversed(order):
        left_height = real_heights[id(node.left)] if node.left is not None else -1
        right_height = real_heights[id(node.right)] if node.right is not None else -1
        real_heights[id(node)] = 1 + max(left_height, right_height)
        max_gap = max(max_gap, abs(left_height - right_height))
        heights_ok = heights_ok and node.height == real_heights[id(node)]
    keys = tree.inorder()
    ordered = all(keys[index] < keys[index + 1] for index in range(len(keys) - 1))
    size_ok = len(order) == tree.size == len(keys)
    return {"heights_ok": heights_ok, "max_imbalance": max_gap, "ordered": ordered,
            "size_ok": size_ok,
            "balanced": heights_ok and ordered and size_ok and max_gap <= 1}


from domain.associations import is_candidate
from domain.models import format_id
from domain.priority import compute_priority, is_populated


def audit_catalog(catalog):
    """Check global BST order, tree metadata, identities, and references."""
    avl = catalog.avl
    errors, imbalance = [], []

    def add_error(event_id, kind, detail):
        errors.append({"event_id": event_id, "kind": kind, "detail": detail})

    nodes, seen, counts = [], set(), {}
    stack = [(avl.root, None, None)] if avl.root is not None else []
    while stack:
        node, lower, upper = stack.pop()
        event_id = node.key.event_id
        if id(node) in seen:
            add_error(event_id, "unicidad", "nodo alcanzable por dos caminos (ciclo o posición duplicada)")
            continue
        seen.add(id(node))
        nodes.append(node)
        counts[event_id] = counts.get(event_id, 0) + 1
        if lower is not None and not node.key > lower:
            add_error(event_id, "orden", f"clave {node.key.as_tuple()} no supera la cota {lower.as_tuple()} de un ancestro")
        if upper is not None and not node.key < upper:
            add_error(event_id, "orden", f"clave {node.key.as_tuple()} no es menor que la cota {upper.as_tuple()} de un ancestro")
        if node.left is not None:
            stack.append((node.left, lower, node.key))
        if node.right is not None:
            stack.append((node.right, node.key, upper))

    for event_id, count in counts.items():
        if count > 1:
            add_error(event_id, "unicidad", f"el identificador aparece en {count} nodos")
    if avl.size != len(nodes):
        add_error(None, "unicidad", f"tamaño almacenado {avl.size} distinto de los nodos alcanzables {len(nodes)}")

    real_heights = {}
    for node in reversed(nodes):
        event_id = node.key.event_id
        left_height = real_heights.get(id(node.left), -1)
        right_height = real_heights.get(id(node.right), -1)
        real_heights[id(node)] = 1 + max(left_height, right_height)
        balance = left_height - right_height
        if node.height != real_heights[id(node)]:
            add_error(event_id, "altura", f"altura almacenada {node.height}, recalculada {real_heights[id(node)]}")
        if avl.balance_factor(node) != balance:
            add_error(event_id, "factor", f"factor almacenado {avl.balance_factor(node)}, recalculado {balance}")
        if abs(balance) > 1:
            imbalance.append({"event_id": event_id, "balance": balance})
            if not avl.stress:
                add_error(event_id, "balance", f"factor {balance} fuera de -1..1 en modo normal")

    node_ids = set(counts)
    for event_id, event in catalog.active.items():
        if event_id not in node_ids:
            add_error(event_id, "referencia", "evento activo sin nodo en el AVL")
        populated = is_populated(event.x, event.y, catalog.zones)
        if event.populated != populated:
            add_error(event_id, "metadatos", "zona poblada almacenada no coincide con la calculada")
        if event.priority != compute_priority(event.magnitude, event.depth, populated):
            add_error(event_id, "metadatos", "prioridad almacenada no coincide con la calculada")
    for node in nodes:
        event = catalog.active.get(node.key.event_id)
        if event is None:
            add_error(node.key.event_id, "referencia", "nodo sin evento activo")
        elif event.key != node.key:
            add_error(node.key.event_id, "metadatos", "la clave del nodo no coincide con los datos del evento")

    known = catalog.known_events()
    for event_id in set(catalog.active) | set(catalog.archived) | set(catalog.deleted):
        if sum(event_id in group for group in
               (catalog.active, catalog.archived, catalog.deleted)) > 1:
            add_error(event_id, "unicidad", "identidad repetida entre activos, histórico y eliminados")
    for event_id, event in known.items():
        reference_id = event.reference_id
        if reference_id is None:
            continue
        target = known.get(reference_id)
        if target is None or reference_id == event_id:
            add_error(event_id, "referencia", f"referencia inválida: {format_id(reference_id)}")
        elif not is_candidate(target, event, catalog.W, catalog.R):
            add_error(event_id, "referencia", f"{format_id(reference_id)} no cumple la regla de candidato")
        else:
            chain, current = {event_id}, target
            while current is not None and current.event_id not in chain:
                chain.add(current.event_id)
                current = known.get(current.reference_id)
            if current is not None:
                add_error(event_id, "referencia", "ciclo en la cadena de referencias")

    by_event = {}
    for error in errors:
        by_event.setdefault(error["event_id"], []).append(
            f"{error['kind']}: {error['detail']}")
    return {"ok": not errors, "mode": "estrés" if avl.stress else "normal",
            "errors": errors, "by_event": by_event, "nodes": len(nodes),
            "expected_imbalance": imbalance if avl.stress else [],
            "max_imbalance": max((abs(item["balance"]) for item in imbalance), default=0),
            "balanced": not errors and not imbalance}
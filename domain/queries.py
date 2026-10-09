"""Measured queries over the active AVL."""

from core.tree_key import TreeKey
from domain.models import PENDING, ValidationError, parse_decimal, parse_id, parse_time

MAX_ID = 999999


def _result(results, examined, note, **extra):
    return {"results": results, "examined": examined, "note": note, **extra}


def top_pending(catalog, k):
    """Return up to k pending events in descending key order."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValidationError("k debe ser un entero positivo")
    results, examined, stack, current = [], 0, [], catalog.avl.root
    while (current is not None or stack) and len(results) < k:
        while current is not None:
            examined += 1
            stack.append(current)
            current = current.right
        node = stack.pop()
        event = catalog.active[node.key.event_id]
        if event.attention == PENDING:
            results.append(event)
        current = node.left
    return _result(results, examined,
                   "Recorrido inorden inverso con parada al reunir k. Peor caso "
                   "O(n): 'pendiente' no forma parte de K, no se puede descartar "
                   "ninguna rama por ese dato.")


def by_magnitude(catalog, low, high):
    """Return events in an inclusive magnitude range, ordered by TreeKey."""
    low = parse_decimal(low, "la magnitud mínima", -2.0, 10.0)
    high = parse_decimal(high, "la magnitud máxima", -2.0, 10.0)
    if low > high:
        raise ValidationError("la magnitud mínima no puede superar la máxima")
    touched, found = set(), []
    for priority in (1, 2, 3):
        lower, upper = (priority, low, 0), (priority, high, MAX_ID + 1)
        stack = [catalog.avl.root] if catalog.avl.root is not None else []
        while stack:
            node = stack.pop()
            touched.add(node.key.event_id)
            key = node.key.as_tuple()
            if lower <= key <= upper:
                found.append(catalog.active[node.key.event_id])
            if key > lower and node.left is not None:
                stack.append(node.left)
            if key < upper and node.right is not None:
                stack.append(node.right)
    found.sort(key=lambda event: event.key.as_tuple())
    return _result(found, len(touched),
                   "Tres búsquedas por rango (una por prioridad). Peor caso "
                   "O(n) si el intervalo cubre todo; si no, O(log n + r) por bloque.")


def shallow_in_dates(catalog, depth_limit, start, end):
    """Filter by hypocenter depth and inclusive UTC time interval."""
    depth_limit = parse_decimal(depth_limit, "el límite de profundidad", 0.0, 700.0)
    start, end = parse_time(start), parse_time(end)
    if start > end:
        raise ValidationError("la fecha inicial no puede ser posterior a la final")
    found, examined, stack = [], 0, []
    if catalog.avl.root is not None:
        stack.append(catalog.avl.root)
    while stack:
        node = stack.pop()
        examined += 1
        event = catalog.active[node.key.event_id]
        if event.depth <= depth_limit and start <= event.time <= end:
            found.append(event)
        for child in (node.left, node.right):
            if child is not None:
                stack.append(child)
    found.sort(key=lambda event: event.key.as_tuple())
    return _result(found, examined,
                   "Recorrido completo, O(n): ni la hora ni la profundidad del "
                   "hipocentro forman parte de K, así que ninguna rama se descarta.")


def associations(catalog, event_id):
    """Return candidate events, the chosen reference, and its dependants."""
    event_id = parse_id(event_id)
    status = catalog.status_of(event_id)
    if status is None:
        raise ValidationError("el identificador no existe")
    event = (catalog.active.get(event_id) or catalog.archived.get(event_id)
             or catalog.deleted.get(event_id))
    if status == "eliminado":
        return _result([], 0, "Evento eliminado: no participa en asociaciones.",
                       event=event, status=status, candidates=[], reference=None,
                       used_by=[])
    examined = catalog.avl.find(event.key)[1] if status == "activo" else 0
    known = catalog.known_events()
    candidate_events = sorted(catalog.candidates_of(event),
                              key=lambda item: (-item.magnitude,
                                                -item.time.timestamp(), item.event_id))
    reference = known.get(event.reference_id)
    used_by = sorted((item for item in known.values()
                      if item.reference_id == event_id), key=lambda item: item.event_id)
    label = lambda item: (item, catalog.status_of(item.event_id))
    labeled = [label(item) for item in candidate_events]
    return _result(labeled, examined,
                   "Los candidatos se buscan en el diccionario de activos+archivados "
                   f"(O(n), {len(known)} entradas); el AVL solo se usa para ubicar "
                   "el evento consultado.",
                   event=event, status=status, candidates=labeled,
                   reference=label(reference) if reference else None,
                   used_by=[label(item) for item in used_by])


def costly_access(catalog):
    """Find priority-3 events deeper than L, pruning subtrees by priority."""
    limit, avl = catalog.L, catalog.avl
    stack = [(avl.root, 0)] if avl.root is not None else []
    examined, hits = 0, []
    while stack:
        node, depth = stack.pop()
        examined += 1
        if node.key.priority == 3 and depth > limit:
            hits.append(node.key)
        if node.right is not None:
            stack.append((node.right, depth + 1))
        if node.key.priority == 3 and node.left is not None:
            stack.append((node.left, depth + 1))
    rows = []
    for key in sorted(hits, reverse=True):
        _, visited = avl.find(key)
        rows.append({"event": catalog.active[key.event_id], "depth": visited - 1,
                     "limit": limit, "visited": visited})
    return _result(rows, examined,
                   "Se descartan los subárboles izquierdos de nodos con P < 3. "
                   "Peor caso O(n) (todo el árbol es prioridad 3).")
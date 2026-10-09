"""Archive eligible branches of old, low-priority events."""

from dataclasses import dataclass, field
from datetime import timedelta

from core.stack import Stack
from domain.models import ValidationError, format_id


@dataclass
class ArchivePlan:
    root_id: int
    root_key: object
    ids: list
    eligible: list
    justification: str = ""
    count: int = field(init=False)

    def __post_init__(self):
        self.count = len(self.ids)


def plan_archive(catalog):
    """Choose the largest fully eligible subtree without changing state."""
    avl = catalog.avl
    if avl.root is None:
        return None
    age_limit = timedelta(hours=catalog.T)

    order, stack = [], Stack()
    stack.push((avl.root, 0))
    while not stack.is_empty():
        node, depth = stack.pop()
        order.append((node, depth))
        for child in (node.left, node.right):
            if child is not None:
                stack.push((child, depth + 1))

    info, eligible = {}, []
    for node, depth in reversed(order):
        event = catalog.active[node.key.event_id]
        is_eligible = (event.priority == 1
                       and catalog.clock - event.time > age_limit)
        size = 1
        for child in (node.left, node.right):
            if child is not None:
                child_size, child_eligible = info[id(child)]
                size += child_size
                is_eligible = is_eligible and child_eligible
        info[id(node)] = (size, is_eligible)
        if is_eligible:
            eligible.append((node, size, depth))
    if not eligible:
        return None

    node, size, depth = max(eligible,
                            key=lambda item: (item[1], item[2], item[0].key.event_id))
    ids, stack = [], Stack()
    stack.push(node)
    while not stack.is_empty():
        current = stack.pop()
        ids.append(current.key.event_id)
        for child in (current.left, current.right):
            if child is not None:
                stack.push(child)

    summary = sorted(((n.key.event_id, count, level) for n, count, level in eligible),
                     key=lambda item: (-item[1], -item[2], -item[0]))
    largest = [item for item in summary if item[1] == size]
    reason = (f"Hay {len(eligible)} subárbol(es) elegible(s). Se elige la raíz "
              f"{format_id(node.key.event_id)} por tener la mayor cantidad de "
              f"nodos ({size}).")
    if len(largest) > 1:
        same_depth = [item for item in largest if item[2] == depth]
        reason += (f" Empate en tamaño con {len(largest) - 1} rama(s): gana la raíz "
                   f"más profunda (profundidad {depth}).")
        if len(same_depth) > 1:
            reason += " Persiste el empate: gana el mayor identificador de raíz."
    return ArchivePlan(node.key.event_id, node.key, sorted(ids), summary, reason)


def execute_archive(catalog, plan):
    """Move the fixed planned subtree from active events into the archive."""
    fixed_ids = list(plan.ids)
    removed = catalog.avl.remove_subtree(plan.root_key)
    if removed != len(fixed_ids):
        raise ValidationError("el subárbol cambió: no coincide con el plan")
    for event_id in fixed_ids:
        catalog.archived[event_id] = catalog.active.pop(event_id)
    catalog.counters["mass_archives"] += 1
    catalog.counters["archived_events"] += len(fixed_ids)
    return fixed_ids
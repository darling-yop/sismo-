"""JSON-friendly capture and exact topology restoration for undo and saves."""

from core.fifo import Queue
from core.node import Node
from core.stack import Stack
from domain.catalog import Catalog
from domain.models import Event, Zone, format_time, parse_time
from domain.reports import Report

SNAPSHOT_VERSION = 1


def _event_to_dict(event):
    return {"id": event.event_id, "magnitude": event.magnitude, "depth": event.depth,
            "x": event.x, "y": event.y, "time": format_time(event.time),
            "revision": event.revision, "stations": sorted(event.stations),
            "attention": event.attention, "populated": event.populated,
            "priority": event.priority, "reference_id": event.reference_id}


def _event_from_dict(data):
    return Event(data["id"], data["magnitude"], data["depth"], data["x"], data["y"],
                 parse_time(data["time"]), data["revision"], set(data["stations"]),
                 data["attention"], data["populated"], data["priority"],
                 data["reference_id"])


event_to_dict, event_from_dict = _event_to_dict, _event_from_dict


def _tree_to_dict(avl):
    nodes, stack = [], Stack()
    if avl.root is not None:
        stack.push(avl.root)
    while not stack.is_empty():
        node = stack.pop()
        nodes.append({"id": node.key.event_id,
                      "left": node.left.key.event_id if node.left else None,
                      "right": node.right.key.event_id if node.right else None,
                      "height": node.height,
                      "balance": avl.balance_factor(node)})
        for child in (node.right, node.left):
            if child is not None:
                stack.push(child)
    return {"root": avl.root.key.event_id if avl.root else None, "nodes": nodes}


def capture(catalog, queue):
    return {
        "version": SNAPSHOT_VERSION,
        "mode": "stress" if catalog.avl.stress else "normal",
        "clock": format_time(catalog.clock),
        "params": {"W": catalog.W, "R": catalog.R, "L": catalog.L, "T": catalog.T},
        "stations": sorted(catalog.stations) if catalog.stations else None,
        "zones": [{"name": zone.name, "x1": zone.x1, "y1": zone.y1, "x2": zone.x2,
                   "y2": zone.y2, "populated": zone.populated} for zone in catalog.zones],
        "tree": _tree_to_dict(catalog.avl),
        "active": [_event_to_dict(catalog.active[event_id])
                   for event_id in sorted(catalog.active)],
        "archived": [_event_to_dict(catalog.archived[event_id])
                     for event_id in sorted(catalog.archived)],
        "deleted": [_event_to_dict(catalog.deleted[event_id])
                    for event_id in sorted(catalog.deleted)],
        "queue": [report.to_dict() for report in queue.to_list()],
        "counters": dict(catalog.counters),
        "rotation_stats": dict(catalog.avl.stats),
    }


def restore(data):
    """Build a new (Catalog, Queue) from a captured state."""
    catalog = Catalog(zones=[Zone(**zone) for zone in data["zones"]],
                      stations=data["stations"], clock=parse_time(data["clock"]))
    params = data["params"]
    catalog.W, catalog.R, catalog.L, catalog.T = (
        params["W"], params["R"], params["L"], params["T"])
    catalog.active = {item["id"]: _event_from_dict(item) for item in data["active"]}
    catalog.archived = {item["id"]: _event_from_dict(item) for item in data["archived"]}
    catalog.deleted = {item["id"]: _event_from_dict(item) for item in data["deleted"]}
    catalog.counters = dict(data["counters"])

    avl = catalog.avl
    nodes = {}
    for entry in data["tree"]["nodes"]:
        node = Node(catalog.active[entry["id"]].key)
        node.height = entry["height"]
        nodes[entry["id"]] = node
    for entry in data["tree"]["nodes"]:
        node = nodes[entry["id"]]
        node.left = nodes.get(entry["left"])
        node.right = nodes.get(entry["right"])
    avl.root = nodes.get(data["tree"]["root"])
    avl.size = len(nodes)
    avl.stress = data["mode"] == "stress"
    avl.stats = dict(data["rotation_stats"])

    queue = Queue()
    for item in data["queue"]:
        queue.enqueue(Report.from_dict(item))
    return catalog, queue
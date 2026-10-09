"""JSON files for structural export, validated loading, and named versions."""

import json
import math
import os
import re
import tempfile

from core.avl import AVL
from core.fifo import Queue
from domain.associations import is_candidate
from domain.audit import audit_catalog
from domain.catalog import Catalog
from domain.comparison import compare
from domain.metrics import COUNTER_NAMES
from domain.models import (ATTENTION_VALUES, ValidationError, Zone, format_id,
                           parse_decimal, parse_id, parse_time)
from domain.priority import compute_priority, is_populated
from domain.reports import REPORT_FIELDS
from services.snapshot import (SNAPSHOT_VERSION, capture, event_from_dict,
                               restore)

KIND_STATE = "sismolab-state"
KIND_VERSION = "sismolab-version"
KIND_INSERTIONS = "sismolab-insertions"
KIND_REPORTS = "sismolab-reports"
DEFAULT_VERSIONS_DIR = os.path.join("data", "versions")
MAX_PROBLEMS = 60


class PersistenceError(Exception):
    """File validation failure with all detected problems."""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        raise PersistenceError([f"no se pudo leer el archivo JSON: {error}"])


def write_json(path, document):
    """Write JSON atomically so failures cannot leave a partial file."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=1)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _zones(raw, problems):
    zones = []
    if not isinstance(raw, list):
        problems.append("las zonas deben ser una lista")
        return zones
    for item in raw:
        try:
            x1, x2 = (parse_decimal(item[key], key, 0.0, 1000.0)
                      for key in ("x1", "x2"))
            y1, y2 = (parse_decimal(item[key], key, 0.0, 1000.0)
                      for key in ("y1", "y2"))
            if x1 > x2 or y1 > y2 or not isinstance(item["populated"], bool):
                raise ValidationError("límites invertidos o 'populated' no booleano")
            zones.append(Zone(str(item["name"]), x1, y1, x2, y2,
                              item["populated"]))
        except (ValidationError, KeyError, TypeError) as error:
            problems.append(f"zona inválida: {error}")
    return zones


def _event(item, zones, clock, stations, group, problems):
    label = f"evento {item.get('id') if isinstance(item, dict) else item!r} ({group})"
    if not isinstance(item, dict):
        problems.append(f"{label}: no es un objeto")
        return None
    try:
        if not _is_int(item["id"]):
            raise ValidationError("el identificador debe ser entero")
        event_id = parse_id(item["id"])
        magnitude = parse_decimal(item["magnitude"], "la magnitud", -2.0, 10.0)
        depth = parse_decimal(item["depth"], "la profundidad", 0.0, 700.0)
        x = parse_decimal(item["x"], "x", 0.0, 1000.0)
        y = parse_decimal(item["y"], "y", 0.0, 1000.0)
        moment = parse_time(item["time"])
        if clock is not None and moment > clock:
            raise ValidationError("la fecha es posterior al reloj")
        if not _is_int(item["revision"]) or item["revision"] < 1:
            raise ValidationError("la revisión debe ser un entero positivo")
        if item["attention"] not in ATTENTION_VALUES:
            raise ValidationError("estado de atención inválido")
        event_stations = item["stations"]
        if (not isinstance(event_stations, list) or not event_stations
                or not all(isinstance(station, str) and station
                           for station in event_stations)
                or (stations is not None
                    and not set(event_stations) <= set(stations))):
            raise ValidationError("estaciones inválidas o desconocidas")
        reference_id = item["reference_id"]
        if reference_id is not None and not _is_int(reference_id):
            raise ValidationError("la referencia debe ser un identificador o null")
        if (not isinstance(item["populated"], bool)
                or not _is_int(item["priority"])):
            raise ValidationError("zona poblada o prioridad con tipo inválido")
    except ValidationError as error:
        problems.append(f"{label}: {error}")
        return None
    except KeyError as error:
        problems.append(f"{label}: falta el campo {error}")
        return None

    populated = is_populated(x, y, zones)
    priority = compute_priority(magnitude, depth, populated)
    if item["populated"] != populated:
        problems.append(f"{label}: la zona poblada almacenada no coincide con la calculada")
    if item["priority"] != priority:
        problems.append(f"{label}: la prioridad almacenada ({item['priority']}) "
                        f"no coincide con la calculada ({priority})")
    event = event_from_dict(item)
    event.populated, event.priority = populated, priority
    return event


def _check_tree(tree, mode, active, problems, warnings):
    add_problem = problems.append
    if (not isinstance(tree, dict) or "root" not in tree
            or not isinstance(tree.get("nodes"), list)):
        add_problem("el árbol debe tener 'root' y una lista 'nodes'")
        return
    nodes = {}
    for node in tree["nodes"]:
        if not isinstance(node, dict) or not all(
                key in node for key in ("id", "left", "right", "height", "balance")):
            add_problem("un nodo no tiene los campos id/left/right/height/balance")
            return
        if node["id"] in nodes:
            add_problem(f"el nodo {node['id']} está repetido")
        nodes[node["id"]] = node
    structural_ok = len(nodes) == len(tree["nodes"])
    by_id = {event.event_id: event for event in active}
    for missing in sorted(set(by_id) - set(nodes)):
        add_problem(f"el evento activo {format_id(missing)} no tiene nodo")
        structural_ok = False
    for extra in sorted(ident for ident in set(nodes) - set(by_id) if _is_int(ident)):
        add_problem(f"el nodo {format_id(extra)} no corresponde a un evento activo")
        structural_ok = False
    root = tree["root"]
    if not nodes:
        if root is not None:
            add_problem("la raíz debe ser null cuando no hay nodos")
        return
    if root not in nodes:
        add_problem("la raíz no es un nodo del árbol")
        return
    parents = {}
    for ident, node in nodes.items():
        for side in ("left", "right"):
            child = node[side]
            if child is None:
                continue
            if child not in nodes:
                add_problem(f"el enlace {side} de {format_id(ident)} apunta a {child}, que no existe")
                structural_ok = False
            elif child == ident:
                add_problem(f"{format_id(ident)} se enlaza a sí mismo")
                structural_ok = False
            elif child in parents:
                add_problem(f"{format_id(child)} ocupa dos posiciones (dos padres)")
                structural_ok = False
            else:
                parents[child] = ident
    if root in parents:
        add_problem("la raíz aparece como hijo de otro nodo (ciclo)")
        structural_ok = False
    if structural_ok:
        reached, stack = set(), [root]
        while stack:
            current = stack.pop()
            if current in reached:
                structural_ok = False
                break
            reached.add(current)
            stack.extend(child for child in (nodes[current]["left"],
                                              nodes[current]["right"])
                         if child is not None)
        if len(reached) != len(nodes):
            add_problem(f"{len(nodes) - len(reached)} nodo(s) inalcanzables desde la raíz (ciclo)")
            structural_ok = False
    if not structural_ok:
        return

    keys = {event_id: (event.priority, event.magnitude, event.event_id)
            for event_id, event in by_id.items()}
    order, stack = [], [(root, None, None)]
    while stack:
        ident, lower, upper = stack.pop()
        order.append(ident)
        key = keys[ident]
        if ((lower is not None and not key > lower)
                or (upper is not None and not key < upper)):
            add_problem(f"orden BST roto en {format_id(ident)}: su clave {key} "
                        "viola la cota de un ancestro")
        node = nodes[ident]
        if node["left"] is not None:
            stack.append((node["left"], lower, key))
        if node["right"] is not None:
            stack.append((node["right"], key, upper))
    real_heights, unbalanced = {}, False
    for ident in reversed(order):
        node = nodes[ident]
        left_height = real_heights.get(node["left"], -1)
        right_height = real_heights.get(node["right"], -1)
        real_heights[ident] = 1 + max(left_height, right_height)
        if node["height"] != real_heights[ident]:
            add_problem(f"altura almacenada de {format_id(ident)} es {node['height']}, "
                        f"la real es {real_heights[ident]}")
        if node["balance"] != left_height - right_height:
            add_problem(f"factor de balance almacenado de {format_id(ident)} es "
                        f"{node['balance']}, el real es {left_height - right_height}")
        unbalanced = unbalanced or abs(left_height - right_height) > 1
    if unbalanced and mode == "normal":
        add_problem("el árbol está desbalanceado: solo puede cargarse en modo estrés")
    elif unbalanced:
        warnings.append("árbol desbalanceado cargado en modo estrés")


def _validate(state, problems, warnings):
    add_problem = problems.append
    if not isinstance(state, dict):
        add_problem("el estado no es un objeto JSON")
        return
    required = ("version", "mode", "clock", "params", "stations", "zones", "tree",
                "active", "archived", "deleted", "queue", "counters", "rotation_stats")
    missing = [key for key in required if key not in state]
    if missing:
        add_problem(f"faltan campos obligatorios: {missing}")
        return
    if state["version"] != SNAPSHOT_VERSION:
        add_problem(f"versión de formato no soportada: {state['version']}")
    if state["mode"] not in ("normal", "stress"):
        add_problem("el modo debe ser 'normal' o 'stress'")
    try:
        clock = parse_time(state["clock"])
    except ValidationError as error:
        add_problem(f"reloj inválido: {error}")
        clock = None
    params = state["params"]
    if not isinstance(params, dict) or set(params) != {"W", "R", "L", "T"}:
        add_problem("los parámetros deben ser exactamente W, R, L y T")
        params = None
    else:
        for name in ("W", "R", "T"):
            if not _is_number(params[name]) or not params[name] > 0:
                add_problem(f"{name} debe ser un número positivo")
        if not _is_int(params["L"]) or params["L"] < 0:
            add_problem("L debe ser un entero no negativo")
    stations = state["stations"]
    if stations is not None and not (isinstance(stations, list)
                                     and all(isinstance(item, str) for item in stations)):
        add_problem("las estaciones deben ser una lista de textos o null")
        stations = None
    zones = _zones(state["zones"], problems)

    events, groups = {}, {}
    for group in ("active", "archived", "deleted"):
        groups[group] = []
        if not isinstance(state[group], list):
            add_problem(f"'{group}' debe ser una lista")
            continue
        for item in state[group]:
            event = _event(item, zones, clock, stations, group, problems)
            if event is None:
                continue
            if event.event_id in events:
                add_problem(f"el identificador {format_id(event.event_id)} está duplicado "
                            "entre activos, histórico y eliminados")
                continue
            events[event.event_id] = event
            groups[group].append(event)

    _check_tree(state["tree"], state["mode"], groups["active"], problems, warnings)
    if params is not None and not any("positivo" in problem for problem in problems):
        known = {event.event_id: event
                 for event in groups["active"] + groups["archived"]}
        for event in known.values():
            if event.reference_id is None:
                continue
            reference = known.get(event.reference_id)
            if reference is None or reference.event_id == event.event_id:
                add_problem(f"{format_id(event.event_id)}: referencia inválida a "
                            f"{event.reference_id} (no existe, está eliminada o es él mismo)")
            elif not is_candidate(reference, event, params["W"], params["R"]):
                add_problem(f"{format_id(event.event_id)}: {format_id(reference.event_id)} "
                            "no es un candidato válido con los parámetros W y R guardados")

    counters = state["counters"]
    if (not isinstance(counters, dict) or set(counters) != set(COUNTER_NAMES)
            or not all(_is_int(value) and value >= 0 for value in counters.values())):
        add_problem("los contadores deben ser enteros no negativos con los nombres esperados")
    stats = state["rotation_stats"]
    if (not isinstance(stats, dict) or set(stats) != set(AVL().stats)
            or not all(_is_int(value) and value >= 0 for value in stats.values())):
        add_problem("las estadísticas de rotación son inválidas")
    if (not isinstance(state["queue"], list) or not all(
            isinstance(report, dict) and all(field in report for field in REPORT_FIELDS)
            for report in state["queue"])):
        add_problem("la cola debe ser una lista de reportes con todos sus campos")


def validate_state(state):
    """Return (problems, warnings); no problems means safe to load."""
    problems, warnings = [], []
    try:
        _validate(state, problems, warnings)
        if not problems:
            catalog, _ = restore(state)
            audit = audit_catalog(catalog)
            for item in audit["errors"]:
                problems.append(f"auditoría: {item['kind']} en evento "
                                f"{item['event_id']}: {item['detail']}")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        problems.append(f"estructura inválida ({type(error).__name__}: {error})")
    if len(problems) > MAX_PROBLEMS:
        problems = problems[:MAX_PROBLEMS] + [f"... y {len(problems) - MAX_PROBLEMS} más"]
    return problems, warnings


def save_state(scenario, path):
    write_json(path, {"kind": KIND_STATE, "state": scenario.snapshot()})


def _document_state(document, kind):
    if not isinstance(document, dict) or document.get("kind") != kind:
        raise PersistenceError([f"el archivo no es de tipo '{kind}'"])
    problems, warnings = validate_state(document.get("state"))
    if problems:
        raise PersistenceError(problems)
    return document["state"], warnings


def load_topology(scenario, path):
    """Validate then restore the saved topology as one undoable action."""
    state, warnings = _document_state(read_json(path), KIND_STATE)
    scenario.restore_state(state, "Carga por topología")
    return {"mode": state["mode"], "warnings": warnings}


def load_insertions(scenario, path):
    """Load validated event insertions and compare AVL with a plain BST."""
    document = read_json(path)
    if not isinstance(document, dict) or document.get("kind") != KIND_INSERTIONS:
        raise PersistenceError([f"el archivo no es de tipo '{KIND_INSERTIONS}'"])
    problems = []
    zones = _zones(document.get("zones", []), problems)
    stations = document.get("stations")
    try:
        clock = parse_time(document["clock"]) if "clock" in document else None
    except ValidationError as error:
        problems.append(f"reloj inválido: {error}")
        clock = None
    events = document.get("events")
    if not isinstance(events, list) or not events:
        problems.append("'events' debe ser una lista no vacía")
        events = []
    catalog = Catalog(zones, stations, clock)
    try:
        catalog.set_parameters(**(document.get("params") or {}))
    except (ValidationError, TypeError) as error:
        problems.append(f"parámetros inválidos: {error}")

    seen, keys = set(), []
    for index, item in enumerate(events, start=1):
        try:
            event_id = parse_id(item["id"])
            if event_id in seen:
                raise ValidationError(f"el identificador {format_id(event_id)} está duplicado en la secuencia")
            seen.add(event_id)
            event = catalog.create(event_id, item["magnitude"], item["depth"],
                                   item["x"], item["y"], item["time"],
                                   item["station"])
            keys.append(event.key)
        except (ValidationError, KeyError, TypeError) as error:
            problems.append(f"evento #{index}: {error}")
    if problems:
        raise PersistenceError(problems)
    comparison = compare(keys)
    scenario.restore_state(capture(catalog, Queue()), "Carga por inserciones")
    return {"comparison": comparison, "order": [key.event_id for key in keys]}


def _version_path(folder, name):
    name = (name or "").strip()
    if not name or len(name) > 60:
        raise ValidationError("el nombre de la versión debe tener entre 1 y 60 caracteres")
    safe_name = re.sub(r"[^\w\- ]", "_", name)
    return name, os.path.join(folder, safe_name + ".json")


def save_version(scenario, name, folder=DEFAULT_VERSIONS_DIR, overwrite=False):
    """Save operational state under a user-visible name."""
    name, path = _version_path(folder, name)
    if os.path.exists(path) and not overwrite:
        raise ValidationError("ya existe una versión con ese nombre")
    write_json(path, {"kind": KIND_VERSION, "name": name, "state": scenario.snapshot()})
    return path


def list_versions(folder=DEFAULT_VERSIONS_DIR):
    versions = []
    if not os.path.isdir(folder):
        return versions
    for filename in sorted(os.listdir(folder)):
        if not filename.endswith(".json"):
            continue
        try:
            document = read_json(os.path.join(folder, filename))
            if document.get("kind") == KIND_VERSION:
                versions.append({"name": document["name"],
                                 "clock": document["state"]["clock"],
                                 "active": len(document["state"]["active"])})
        except (PersistenceError, KeyError, AttributeError, TypeError):
            continue
    return versions


def restore_version(scenario, name, folder=DEFAULT_VERSIONS_DIR):
    """Restore one saved version as a single undoable action."""
    name, path = _version_path(folder, name)
    if not os.path.exists(path):
        raise ValidationError("no existe una versión con ese nombre")
    state, warnings = _document_state(read_json(path), KIND_VERSION)
    scenario.restore_state(state, f"Restaurar versión '{name}'")
    return {"mode": state["mode"], "warnings": warnings}


def load_reports(path):
    """Read a burst file atomically and return its reports without enqueueing."""
    from domain.reports import Report

    document = read_json(path)
    if not isinstance(document, dict) or document.get("kind") != KIND_REPORTS:
        raise PersistenceError([f"el archivo no es de tipo '{KIND_REPORTS}'"])
    items = document.get("reports")
    if not isinstance(items, list) or not items:
        raise PersistenceError(["'reports' debe ser una lista no vacía"])
    problems, reports = [], []
    for index, item in enumerate(items, start=1):
        missing = [field for field in REPORT_FIELDS
                   if not isinstance(item, dict) or field not in item]
        if missing:
            problems.append(f"reporte #{index}: faltan campos {missing}")
            continue
        reports.append(Report.from_dict(item))
    if problems:
        raise PersistenceError(problems)
    return reports
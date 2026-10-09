"""Canvas drawing for the tree and the plane. No Tkinter import: it only calls
canvas methods (create_line/rectangle/oval/text), so tests use a fake canvas.

Visual language (priority and costly access are never confused):
  fill colour      = priority   (red high, orange medium, green low)
  thick purple dashed border + diamond = costly access
  blue border      = selected node
  red caption      = balance factor outside -1..1 (stress imbalance)
"""

BOX_W, BOX_H, GAP_X, GAP_Y, MARGIN = 84, 40, 12, 34, 24
PRIORITY_COLORS = {3: "#e53935", 2: "#fb8c00", 1: "#66bb6a"}
PRIORITY_NAMES = {3: "alta", 2: "media", 1: "baja"}
COSTLY_COLOR, SELECT_COLOR, BAD_COLOR = "#6a1b9a", "#1565c0", "#b71c1c"


def tree_size(layout):
    width = MARGIN * 2 + max(layout.columns, 1) * (BOX_W + GAP_X)
    height = MARGIN * 2 + max(layout.levels, 1) * (BOX_H + GAP_Y) + 20
    return width, height


def _pos(node):
    x = MARGIN + node.column * (BOX_W + GAP_X)
    y = MARGIN + node.depth * (BOX_H + GAP_Y)
    return x, y


def draw_tree(canvas, layout, events, costly=(), imbalanced=(), selected=None, title=""):
    """Draw `layout`. Returns [(event_id, x1, y1, x2, y2)] for click detection."""
    canvas.delete("all")
    width, height = tree_size(layout)
    canvas.configure(scrollregion=(0, 0, width, height))
    if title:
        canvas.create_text(8, 8, text=title, anchor="nw", font=("Segoe UI", 10, "bold"))
    if not layout.nodes:
        canvas.create_text(width / 2 + 100, 80, text="Árbol vacío", font=("Segoe UI", 12))
        return []
    for node in layout.nodes.values():          # edges first (below the boxes)
        x, y = _pos(node)
        for child_id in (node.left, node.right):
            if child_id is None:
                continue
            cx, cy = _pos(layout.nodes[child_id])
            canvas.create_line(x + BOX_W / 2, y + BOX_H, cx + BOX_W / 2, cy,
                               fill="#555555", width=2)
            side = "izq" if child_id == node.left else "der"
            canvas.create_text((x + cx) / 2 + BOX_W / 2, (y + BOX_H + cy) / 2 - 2,
                               text=side, fill="#777777", font=("Segoe UI", 7))
    hits = []
    for eid, node in layout.nodes.items():
        x, y = _pos(node)
        p, m, i = node.key
        event = events.get(eid)
        fill = PRIORITY_COLORS.get(p, "#bdbdbd")
        is_costly = eid in costly
        outline, border, dash = "#333333", 1, None
        if is_costly:
            outline, border, dash = COSTLY_COLOR, 4, (4, 2)
        if eid == selected:
            outline, border, dash = SELECT_COLOR, 4, None
        canvas.create_rectangle(x, y, x + BOX_W, y + BOX_H, fill=fill, outline=outline,
                                width=border, dash=dash)
        if is_costly:
            canvas.create_text(x + BOX_W - 8, y + 8, text="◆", fill=COSTLY_COLOR,
                               font=("Segoe UI", 10, "bold"))
        canvas.create_text(x + BOX_W / 2, y + 12, text=f"SIS-{i:06d}",
                           font=("Segoe UI", 8, "bold"))
        flag = "" if event is None or event.attention == "pendiente" else " ✓"
        canvas.create_text(x + BOX_W / 2, y + 28, text=f"P{p} · M{m}{flag}", font=("Segoe UI", 8))
        bad = eid in imbalanced or abs(node.balance) > 1
        canvas.create_text(x + BOX_W / 2, y + BOX_H + 8,
                           text=f"h{node.height} fb{node.balance:+d}" + (" ¡" if bad else ""),
                           fill=BAD_COLOR if bad else "#555555",
                           font=("Segoe UI", 8, "bold" if bad else "normal"))
        if node.hidden_below:
            canvas.create_text(x + BOX_W / 2, y + BOX_H + 20, text=f"+{node.hidden_below} más",
                               fill="#777777", font=("Segoe UI", 8, "italic"))
        hits.append((eid, x, y, x + BOX_W, y + BOX_H))
    if layout.hidden:
        canvas.create_text(8, height - 14, anchor="sw", fill="#777777",
                           text=f"Se dibujan {layout.levels} niveles; {layout.hidden} nodo(s) más profundos no se muestran.")
    return hits


def draw_legend(canvas, x=8, y=8):
    items = [("alta", PRIORITY_COLORS[3]), ("media", PRIORITY_COLORS[2]), ("baja", PRIORITY_COLORS[1])]
    cursor = x
    canvas.create_text(cursor, y, text="Prioridad:", anchor="nw", font=("Segoe UI", 8, "bold"))
    cursor += 62
    for name, color in items:
        canvas.create_rectangle(cursor, y, cursor + 14, y + 14, fill=color)
        canvas.create_text(cursor + 18, y, text=name, anchor="nw", font=("Segoe UI", 8))
        cursor += 62
    canvas.create_rectangle(cursor, y, cursor + 14, y + 14, outline=COSTLY_COLOR, width=3, dash=(3, 1))
    canvas.create_text(cursor + 18, y, text="◆ acceso costoso", anchor="nw", font=("Segoe UI", 8))
    cursor += 120
    canvas.create_text(cursor, y, text="fb = factor de balance, h = altura, ✓ = revisado",
                       anchor="nw", font=("Segoe UI", 8))


# ---------- geographic plane ----------

def draw_plane(canvas, view, size=640, selected=None):
    """Plane 0-1000 km. Zones = rectangles; events = circles (radius ~ magnitude).

    Filled circle = active event (priority colour), hollow grey dashed = archived,
    purple ring = costly access, grey dashed line = event -> its reference.
    Returns [(event_id, cx, cy, r)].
    """
    canvas.delete("all")
    pad = 36
    scale = size / 1000.0
    total = size + pad * 2
    canvas.configure(scrollregion=(0, 0, total, total))
    px = lambda x: pad + x * scale
    py = lambda y: pad + (1000 - y) * scale           # y grows upwards
    for zone in view["zones"]:
        fill = "#fff3c4" if zone.populated else "#e3e8ec"
        canvas.create_rectangle(px(zone.x1), py(zone.y2), px(zone.x2), py(zone.y1),
                                fill=fill, outline="#8d8d8d")
        canvas.create_text(px(zone.x1) + 4, py(zone.y2) + 3, anchor="nw", font=("Segoe UI", 8, "bold"),
                           text=f"{zone.name} ({'poblada' if zone.populated else 'no poblada'})")
    for tick in range(0, 1001, 100):
        canvas.create_line(px(tick), py(0), px(tick), py(1000), fill="#dddddd")
        canvas.create_line(px(0), py(tick), px(1000), py(tick), fill="#dddddd")
        canvas.create_text(px(tick), py(0) + 12, text=str(tick), font=("Segoe UI", 7))
        canvas.create_text(pad - 6, py(tick), text=str(tick), anchor="e", font=("Segoe UI", 7))
    canvas.create_text(total / 2, total - 6, text="x (km)", font=("Segoe UI", 8))
    canvas.create_text(8, 8, text="y (km)", anchor="nw", font=("Segoe UI", 8))

    events = {e.event_id: e for e in view["active"] + view["archived"]}
    for e in events.values():                          # reference links
        ref = events.get(e.reference_id)
        if ref is not None:
            canvas.create_line(px(e.x), py(e.y), px(ref.x), py(ref.y), fill="#777777", dash=(2, 3))
    hits = []
    archived = {e.event_id for e in view["archived"]}
    for e in events.values():
        cx, cy, r = px(e.x), py(e.y), max(4.0, 3.0 + e.magnitude * 1.6)
        if e.event_id in archived:
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#757575", dash=(3, 2), width=2)
        else:
            outline, width = ("#333333", 1)
            if e.event_id in view["costly"]:
                outline, width = COSTLY_COLOR, 3
            if e.event_id == selected:
                outline, width = SELECT_COLOR, 3
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                               fill=PRIORITY_COLORS.get(e.priority, "#bdbdbd"),
                               outline=outline, width=width)
        canvas.create_text(cx + r + 2, cy - r, text=str(e.event_id), anchor="sw", font=("Segoe UI", 7))
        hits.append((e.event_id, cx, cy, r))
    return hits


def hit_node(hits, x, y):
    for eid, x1, y1, x2, y2 in hits:
        if x1 <= x <= x2 and y1 <= y <= y2:
            return eid
    return None


def hit_point(hits, x, y):
    best = None
    for eid, cx, cy, r in hits:
        d = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
        if d <= r + 3 and (best is None or d < best[0]):
            best = (d, eid)
    return best[1] if best else None

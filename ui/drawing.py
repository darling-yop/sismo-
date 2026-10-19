"""Canvas drawing for the tree and the plane. No Tkinter import: it only calls
canvas methods (create_line/rectangle/oval/text), so tests use a fake canvas.

Visual language (priority and costly access are never confused):
  fill colour      = priority
  purple dashed border + diamond = costly access
  cyan border      = selected node
"""

from math import ceil

from ui.theme import FONTS, PALETTE, PRIORITY_COLORS, PRIORITY_NAMES

BOX_W, BOX_H, GAP_X, GAP_Y, MARGIN = 112, 62, 24, 104, 32
COSTLY_COLOR = PALETTE["violet"]
SELECT_COLOR = PALETTE["cyan"]
BAD_COLOR = PALETTE["high"]


def tree_size(layout):
    width = MARGIN * 2 + max(layout.columns, 1) * (BOX_W + GAP_X)
    height = MARGIN * 2 + max(layout.levels, 1) * (BOX_H + GAP_Y) + 20
    return width, height


def _pos(node):
    x = MARGIN + node.column * (BOX_W + GAP_X)
    y = MARGIN + node.depth * (BOX_H + GAP_Y)
    return x, y


def draw_tree(canvas, layout, events, costly=(), imbalanced=(), selected=None, title="",
              rotated=()):
    """Draw `layout`. Returns [(event_id, x1, y1, x2, y2)] for click detection."""
    canvas.delete("all")
    width, height = tree_size(layout)
    if not layout.nodes:
        try:
            viewport_width = max(int(canvas.winfo_width()), int(canvas.cget("width") or 0), width)
            viewport_height = max(int(canvas.winfo_height()), int(canvas.cget("height") or 0), height)
        except (AttributeError, TypeError, ValueError):
            viewport_width, viewport_height = width, height
        canvas.configure(scrollregion=(0, 0, viewport_width, viewport_height))
        canvas.create_text(viewport_width / 2, viewport_height / 2,
                           text="Crea un evento para empezar", fill=PALETTE["muted"],
                           font=FONTS["heading"], anchor="center")
        return []
    canvas.configure(scrollregion=(0, 0, width, height))
    for node in layout.nodes.values():          # edges first (below the boxes)
        x, y = _pos(node)
        for child_id in (node.left, node.right):
            if child_id is None:
                continue
            cx, cy = _pos(layout.nodes[child_id])
            parent_x, child_x = x + BOX_W / 2, cx + BOX_W / 2
            branch_y = y + BOX_H + 8
            canvas.create_line(parent_x, y + BOX_H, parent_x, branch_y,
                               child_x, branch_y, child_x, cy,
                               fill=PALETTE["muted"], width=2)
    hits = []
    for eid, node in layout.nodes.items():
        x, y = _pos(node)
        p, m, i = node.key
        event = events.get(eid)
        fill = PRIORITY_COLORS.get(p, PALETTE["surface_alt"])
        is_costly = eid in costly
        outline, border, dash = PALETTE["border"], 1, None
        if is_costly:
            outline, border, dash = COSTLY_COLOR, 4, (4, 2)
        if eid in rotated:
            outline, border, dash = PALETTE["warning"], 4, None
        if eid == selected:
            outline, border, dash = SELECT_COLOR, 4, None
        tags = ("rotation-highlight",) if eid in rotated else ()
        canvas.create_rectangle(x, y, x + BOX_W, y + BOX_H, fill=fill, outline=outline,
                                width=border, dash=dash, tags=tags)
        if is_costly:
            canvas.create_text(x + BOX_W - 9, y + 9, text="◆", fill=COSTLY_COLOR,
                               font=FONTS["ui_small"])
        canvas.create_text(x + BOX_W / 2, y + 15, text=f"SIS-{i:06d}",
                           fill=PALETTE["black"], font=FONTS["ui_small"])
        magnitude = event.magnitude if event is not None else m
        canvas.create_text(x + BOX_W / 2, y + 40, text=f"M {magnitude:.1f}",
                           fill=PALETTE["black"], font=FONTS["heading"])
        flag = "" if event is None or event.attention == "pendiente" else " ✓"
        canvas.create_text(x + BOX_W / 2, y + BOX_H + 14,
                           text=f"h {node.height}   fb {node.balance:+d}{flag}"
                           + (" ¡" if eid in imbalanced or abs(node.balance) > 1 else ""),
                           fill=BAD_COLOR if eid in imbalanced or abs(node.balance) > 1
                           else PALETTE["muted"], font=FONTS["mono_small"])
        if node.hidden_below:
            canvas.create_text(x + BOX_W / 2, y + BOX_H + 28,
                               text=f"+{node.hidden_below} más",
                               fill=PALETTE["muted"], font=FONTS["ui_small"])
        hits.append((eid, x, y, x + BOX_W, y + BOX_H))
    if layout.hidden:
        canvas.create_text(8, height - 14, anchor="sw", fill=PALETTE["muted"],
                           text=f"Se dibujan {layout.levels} niveles; {layout.hidden} nodo(s) más profundos no se muestran.")
    return hits


def draw_legend(canvas, x=8, y=8):
    items = [("alta", PRIORITY_COLORS[3]), ("media", PRIORITY_COLORS[2]), ("baja", PRIORITY_COLORS[1])]
    cursor = x
    canvas.create_text(cursor, y, text="Prioridad:", anchor="nw", fill=PALETTE["text"],
                       font=FONTS["ui_bold"])
    cursor += 62
    for name, color in items:
        canvas.create_rectangle(cursor, y, cursor + 14, y + 14, fill=color)
        canvas.create_text(cursor + 18, y, text=name, anchor="nw", fill=PALETTE["text"],
                           font=FONTS["ui_small"])
        cursor += 62
    canvas.create_rectangle(cursor, y, cursor + 14, y + 14, outline=COSTLY_COLOR, width=3, dash=(3, 1))
    canvas.create_text(cursor + 18, y, text="◆ acceso costoso", anchor="nw",
                       fill=PALETTE["text"], font=FONTS["ui_small"])
    cursor += 120
    canvas.create_text(cursor, y, text="fb = factor de balance, h = altura, ✓ = revisado",
                       anchor="nw", fill=PALETTE["muted"], font=FONTS["ui_small"])


# ---------- geographic plane ----------

def draw_plane(canvas, view, size=640, selected=None):
    """Draw a zoom-to-events plane with zones, priorities, and reference links.

    Filled circle = active event (priority colour), hollow grey dashed = archived,
    purple ring = costly access, grey dashed line = event -> its reference.
    Returns [(event_id, cx, cy, r)].
    """
    canvas.delete("all")
    pad = 36
    total = size + pad * 2
    canvas.configure(scrollregion=(0, 0, total, total))

    events = {e.event_id: e for e in view["active"] + view["archived"]}
    if events:
        xs = [event.x for event in events.values()]
        ys = [event.y for event in events.values()]
        span = min(1000.0, max(max(xs) - min(xs), max(ys) - min(ys), 100.0) * 1.3)
        x_min = min(1000.0 - span, max(0.0, (min(xs) + max(xs) - span) / 2))
        y_min = min(1000.0 - span, max(0.0, (min(ys) + max(ys) - span) / 2))
    else:
        x_min = y_min = 0.0
        span = 1000.0

    scale = size / span
    x_max, y_max = x_min + span, y_min + span
    px = lambda x: pad + (x - x_min) * scale
    py = lambda y: pad + (y_max - y) * scale           # y grows upwards
    for zone in view["zones"]:
        fill = PALETTE["zone_populated"] if zone.populated else PALETTE["zone_empty"]
        canvas.create_rectangle(px(zone.x1), py(zone.y2), px(zone.x2), py(zone.y1),
                                fill=fill, outline=PALETTE["border"])
        canvas.create_text(px(zone.x1) + 4, py(zone.y2) + 3, anchor="nw",
                           fill=PALETTE["text"], font=FONTS["ui_small"],
                           text=f"{zone.name} ({'poblada' if zone.populated else 'no poblada'})")
    interval = 100 if span > 700 else 50 if span > 350 else 20 if span > 140 else 10
    x_ticks = range(ceil(x_min / interval) * interval, int(x_max) + 1, interval)
    y_ticks = range(ceil(y_min / interval) * interval, int(y_max) + 1, interval)
    for tick in x_ticks:
        canvas.create_line(px(tick), py(y_min), px(tick), py(y_max), fill=PALETTE["grid"])
        canvas.create_text(px(tick), py(y_min) + 12, text=str(tick), fill=PALETTE["muted"],
                           font=FONTS["ui_small"])
    for tick in y_ticks:
        canvas.create_line(px(x_min), py(tick), px(x_max), py(tick), fill=PALETTE["grid"])
        canvas.create_text(pad - 6, py(tick), text=str(tick), anchor="e",
                           fill=PALETTE["muted"], font=FONTS["ui_small"])
    canvas.create_text(total / 2, total - 6, text="x (km)", fill=PALETTE["muted"],
                       font=FONTS["ui_small"])
    canvas.create_text(8, 8, text="y (km)", anchor="nw", fill=PALETTE["muted"],
                       font=FONTS["ui_small"])

    for e in events.values():                          # reference links
        ref = events.get(e.reference_id)
        if ref is not None:
            canvas.create_line(px(e.x), py(e.y), px(ref.x), py(ref.y),
                               fill=PALETTE["muted"], dash=(2, 3))
    hits = []
    archived = {e.event_id for e in view["archived"]}
    for e in events.values():
        cx, cy, r = px(e.x), py(e.y), max(4.0, 3.0 + e.magnitude * 1.6)
        if e.event_id in archived:
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                               outline=PALETTE["archived"], dash=(3, 2), width=2)
        else:
            outline, width = (PALETTE["border"], 1)
            if e.event_id in view["costly"]:
                outline, width = COSTLY_COLOR, 3
            if e.event_id == selected:
                outline, width = SELECT_COLOR, 3
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                               fill=PRIORITY_COLORS.get(e.priority, PALETTE["surface_alt"]),
                               outline=outline, width=width)
        canvas.create_text(cx + r + 2, cy - r, text=str(e.event_id), anchor="sw",
                           fill=PALETTE["text"], font=FONTS["ui_small"])
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

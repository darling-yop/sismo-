"""SismoLab AVL - Tkinter interface.

Only presentation: every action goes through ui.controller.Controller (which
uses Scenario). No widget class is subclassed, so the file stays easy to read.
Run:  python -m ui.app     (or: python main.py)
"""

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from domain.metrics import indicators
from domain.models import ValidationError, format_time, parse_decimal, parse_id, parse_time
from services.persistence import DEFAULT_VERSIONS_DIR
from ui import drawing
from ui.controller import Controller, Outcome, sid
from ui import theme, tree_canvas, widgets

JSON_TYPES = [("Archivos JSON", "*.json"), ("Todos los archivos", "*.*")]
BURST_FIELDS = [("station", "Estación"), ("event_id", "Evento (id)"), ("revision", "Revisión"),
                ("magnitude", "Magnitud"), ("depth", "Prof. H (km)"), ("x", "x (km)"),
                ("y", "y (km)"), ("time", "Hora ISO UTC")]
EVENT_FIELDS = [("id", "ID (p. ej. SIS-12)"), ("magnitude", "Magnitud M (1 decimal)"),
                ("depth", "Prof. H (km)"),
                ("x", "x (km)"), ("y", "y (km)"), ("time", "Hora ISO UTC"), ("station", "Estación")]
CORRECT_FIELDS = [("magnitude", "Magnitud"), ("depth", "Profundidad H"), ("x", "x"), ("y", "y"),
                  ("time", "Hora ISO UTC")]
EVENT_COLUMNS = [("id", 90), ("estado", 70), ("P", 30), ("M", 40), ("H", 45), ("x", 50), ("y", 50),
                 ("hora", 135), ("rev", 35), ("atención", 70), ("prof. nodo", 70),
                 ("costoso", 55), ("referencia", 90)]


# ---------- small widget helpers ----------

def form(parent, fields, row=0, defaults=None, width=18, on_enter=None):
    """Grid of label + entry. Returns {name: StringVar}."""
    variables = {}
    for offset, (name, label) in enumerate(fields):
        field_row = row + offset * 2
        ttk.Label(parent, text=label).grid(row=field_row, column=0, sticky="w", padx=3, pady=(4, 1))
        var = tk.StringVar(value=(defaults or {}).get(name, ""))
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.grid(row=field_row + 1, column=0, sticky="ew", padx=3, pady=(0, 3))
        if on_enter:
            entry.bind("<Return>", lambda _event, callback=on_enter: callback())
        variables[name] = var
    parent.columnconfigure(0, weight=1)
    return variables


def table(parent, columns, height=10):
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[c for c, _ in columns], show="headings", height=height)
    for name, width in columns:
        tree.heading(name, text=name)
        tree.column(name, width=width, anchor="w")
    bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=bar.set)
    tree.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    return frame, tree


def fill(tree, rows):
    tree.delete(*tree.get_children())
    for row in rows:
        tree.insert("", "end", values=row)


def text_box(parent, height=8, width=60):
    frame = ttk.Frame(parent)
    box = tk.Text(frame, height=height, width=width, wrap="word", font=theme.FONTS["mono"],
                  bg=theme.PALETTE["surface"], fg=theme.PALETTE["text"],
                  insertbackground=theme.PALETTE["text"], relief="flat",
                  highlightthickness=0, borderwidth=0)
    bar = ttk.Scrollbar(frame, orient="vertical", command=box.yview)
    box.configure(yscrollcommand=bar.set, state="disabled")
    box.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    return frame, box


def set_text(box, content):
    box.configure(state="normal")
    box.delete("1.0", "end")
    box.insert("1.0", content)
    box.configure(state="disabled")


def canvas_with_bars(parent, width=600, height=400):
    frame = ttk.Frame(parent)
    canvas = tk.Canvas(frame, width=width, height=height, bg=theme.PALETTE["background"],
                       highlightthickness=0)
    hbar = ttk.Scrollbar(frame, orient="horizontal", command=canvas.xview)
    vbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
    hbar.pack(side="bottom", fill="x")
    vbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    return frame, canvas


class App:
    def __init__(self, root, controller=None):
        self.root = root
        self.ctl = controller or Controller()
        self.selected = None              # selected event id
        self.running = False              # continuous queue processing
        self._queue_after = None
        self.versions_folder = tk.StringVar(value=DEFAULT_VERSIONS_DIR)
        self.tab_refresh = {}
        self.tree_hits, self.plane_hits, self.draft = [], [], []
        self.new_vars = {
            name: tk.StringVar(value=format_time(self.ctl.catalog.clock) if name == "time" else "")
            for name, _label in EVENT_FIELDS
        }
        self.fix_id = tk.StringVar()
        self.fix_vars = {name: tk.StringVar() for name, _label in CORRECT_FIELDS}
        self._quick_touched = set()
        self._tree_structure = None
        self._rotation_stats = None
        self._rotated_nodes = set()
        self._rotation_after = None
        self._rotation_animation = None
        self._rotation_frame = 0
        self._stress_flash = False
        theme.configure_styles(root)
        root.configure(bg=theme.PALETTE["background"])
        root.title("SismoLab AVL")
        root.geometry("1440x900")
        self._build_toolbar()
        self._build_metrics()
        self._build_notebook()
        self._build_log()
        self._build_sidebar()
        self._build_inspector()
        self.say(self._ok("Bienvenida a SismoLab AVL. Cargue un archivo o cree eventos."))
        self.refresh()
        if hasattr(root, "_w"):
            self._blink_stress()

    # ---------- feedback ----------

    @staticmethod
    def _ok(text):
        return Outcome(True, text)

    def say(self, outcome, popup=False):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] {'' if outcome.ok else 'ERROR: '}{outcome.message}\n",
                        "ok" if outcome.ok else "error")
        self.log.see("end")
        self.log.configure(state="disabled")
        if not outcome.ok and popup:
            messagebox.showerror("SismoLab AVL", outcome.message)

    def act(self, outcome, popup=True):
        """Show the outcome and redraw everything that may have changed."""
        self.say(outcome, popup=popup)
        self.refresh()
        return outcome.ok

    def confirm(self, title, preview_outcome):
        """Show the affected event BEFORE acting. True if the user accepts."""
        if not preview_outcome.ok:
            self.say(preview_outcome, popup=True)
            return False
        return messagebox.askyesno(title, preview_outcome.message + "\n\n¿Continuar?")

    # ---------- toolbar, log ----------

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=(12, 9))
        bar.pack(fill="x")
        ttk.Label(bar, text="◈ SISMO / AVL", style="Brand.TLabel").pack(side="left", padx=(0, 16))
        self.clock_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self.clock_label.pack(side="left", padx=8)
        self.mode_badge = ttk.Label(bar, text="NORMAL", style="ModeNormal.TLabel")
        self.mode_badge.pack(side="left", padx=8)
        self.stress_btn = ttk.Button(bar, text="Cambiar modo", command=self.toggle_stress)
        self.stress_btn.pack(side="left", padx=4)
        ttk.Button(bar, text="Deshacer  Ctrl+Z", command=lambda: self.act(self.ctl.undo())
                   ).pack(side="right", padx=3)
        self.hours = tk.StringVar(value="24")
        ttk.Button(bar, text="Avanzar reloj", command=lambda: self.act(
            self.ctl.advance_clock(self.hours.get()))).pack(side="right", padx=3)
        ttk.Entry(bar, textvariable=self.hours, width=5).pack(side="right", padx=3)
        ttk.Label(bar, text="+ horas", style="Muted.TLabel").pack(side="right", padx=3)
        ttk.Button(bar, text="Recuperar AVL", command=lambda: self.act(self.ctl.recover())
                   ).pack(side="right", padx=3)
        ttk.Button(bar, text="Reanudar cola", command=lambda: self.act(self.ctl.resume())
                   ).pack(side="right", padx=3)
        self.stress_btn.configure(style="TButton")
        self.root.bind("<Control-z>", lambda _event: self.act(self.ctl.undo()))
        self.root.bind("<Control-Z>", lambda _event: self.act(self.ctl.undo()))
        self.params = {}
        for name in ("W", "R", "L", "T"):
            self.params[name] = tk.StringVar()
        self.banner = ttk.Label(self.root, text="", style="Banner.TLabel")

    def _build_metrics(self):
        strip = ttk.Frame(self.root, padding=(8, 4))
        strip.pack(fill="x")
        self.metric_values = {}
        specs = (("activos", "ACTIVOS"), ("archived", "ARCHIVADOS"),
                 ("deleted", "ELIMINADOS"), ("queue", "COLA"), ("pending", "PENDIENTES"),
                 ("costly_access", "COSTOSOS"), ("height", "ALTURA"), ("leaves", "HOJAS"),
                 ("balance", "BALANCE"), ("LL", "LL"), ("RR", "RR"), ("LR", "LR"), ("RL", "RL"))
        for column, (key, title) in enumerate(specs):
            card, value = widgets.metric_card(strip, title)
            card.grid(row=0, column=column, sticky="ew", padx=2)
            strip.columnconfigure(column, weight=1)
            self.metric_values[key] = value

    def _build_log(self):
        log_panel = ttk.Frame(self.root, style="Surface.TFrame", padding=(8, 5))
        log_panel.pack(fill="x", padx=8, pady=(0, 7))
        ttk.Label(log_panel, text="REGISTRO DE ACCIONES · qué ocurrió y por qué",
                  style="Card.TLabel").pack(anchor="w")
        frame, self.log = text_box(log_panel, height=4, width=150)
        self.log.tag_configure("error", foreground=theme.PALETTE["error"])
        self.log.tag_configure("ok", foreground=theme.PALETTE["ok"])
        frame.pack(fill="x", pady=(4, 0))

    def toggle_stress(self):
        self.act(self.ctl.set_stress(not self.ctl.catalog.avl.stress))

    def apply_params(self):
        self.act(self.ctl.set_parameters(*(self.params[n].get() for n in ("W", "R", "L", "T"))))

    # ---------- notebook ----------

    def _build_notebook(self):
        workspace = ttk.Frame(self.root)
        workspace.pack(fill="both", expand=True, padx=8, pady=(2, 7))
        sidebar_frame = ttk.Frame(workspace, style="Surface.TFrame", width=278)
        sidebar_frame.pack(side="left", fill="y", padx=(0, 7))
        sidebar_frame.pack_propagate(False)
        self.sidebar_canvas = tk.Canvas(
            sidebar_frame, bg=theme.PALETTE["surface"], highlightthickness=0)
        self.sidebar_scrollbar = ttk.Scrollbar(
            sidebar_frame, orient="vertical", command=self.sidebar_canvas.yview)
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)
        self.sidebar_scrollbar.pack(side="right", fill="y")
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)
        self.sidebar = ttk.Frame(self.sidebar_canvas, style="Surface.TFrame", padding=7)
        self._sidebar_window = self.sidebar_canvas.create_window(
            (0, 0), window=self.sidebar, anchor="nw")
        self.sidebar.bind(
            "<Configure>",
            lambda _event: self.sidebar_canvas.configure(
                scrollregion=self.sidebar_canvas.bbox("all")))
        self.sidebar_canvas.bind(
            "<Configure>",
            lambda event: self.sidebar_canvas.itemconfigure(
                self._sidebar_window, width=event.width))
        self.inspector = ttk.Frame(workspace, style="Surface.TFrame", width=278, padding=7)
        self.inspector.pack(side="right", fill="y", padx=(7, 0))
        self.inspector.pack_propagate(False)
        center = ttk.Frame(workspace)
        center.pack(side="left", fill="both", expand=True)
        self.workspace = workspace
        self.nb = ttk.Notebook(center)
        self.nb.pack(fill="both", expand=True)
        builders = [("Árbol AVL", self._tab_tree), ("BST", self._tab_compare),
                    ("Plano", self._tab_plane), ("Eventos", self._tab_events),
                    ("Cola", self._tab_queue), ("Histórico", self._tab_history),
                    ("Archivos", self._tab_files), ("Auditoría", self._tab_audit),
                    ("Consultas", self._tab_queries), ("Indicadores", self._tab_indicators)]
        self.tab_names = []
        for name, build in builders:
            frame = ttk.Frame(self.nb)
            self.nb.add(frame, text=name)
            self.tab_refresh[name] = build(frame)
            self.tab_names.append(name)
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self.refresh())

    def refresh(self):
        c = self.ctl.catalog
        self.stress_btn.configure(text="Cambiar modo")
        self.mode_badge.configure(text="ESTRÉS" if c.avl.stress else "NORMAL",
                                  style="ModeStress.TLabel" if c.avl.stress else "ModeNormal.TLabel")
        self.clock_label.configure(text=f"UTC SIMULADO · {format_time(c.clock)}"
                                        f"{' · COLA EN PAUSA' if self.ctl.sc.paused else ''}")
        for name, value in (("W", c.W), ("R", c.R), ("L", c.L), ("T", c.T)):
            self.params[name].set(str(value))
        self._refresh_metrics()
        self._refresh_active_events()
        self._refresh_inspector()
        view_banner = self.ctl.tree_view(1)["banner"]
        if view_banner:
            self.banner.configure(text=view_banner)
            self.banner.pack(fill="x", padx=8, before=self.workspace)
        else:
            self.banner.pack_forget()
        index = self.nb.index(self.nb.select())
        refresher = self.tab_refresh.get(self.tab_names[index]) if self.tab_names else None
        if refresher:
            refresher()

    def _refresh_metrics(self):
        data = indicators(self.ctl.catalog, self.ctl.queue)
        c = self.ctl.catalog
        root = c.avl.root
        balance = 0 if root is None else c.avl.balance_factor(root)
        values = {
            "activos": data["active"], "archived": data["archived"],
            "deleted": data["deleted"], "queue": data["queue"],
            "pending": data["pending"], "costly_access": data["costly_access"],
            "height": data["height"], "leaves": data["leaves"], "balance": f"{balance:+d}",
            **{case: data["rotations"][case] for case in ("LL", "RR", "LR", "RL")},
        }
        for name, value in values.items():
            self.metric_values[name].configure(text=str(value))

    def _build_sidebar(self):
        ttk.Label(self.sidebar, text="OPERACIONES", style="Card.TLabel").pack(anchor="w", pady=(1, 7))

        card, body = widgets.collapsible_card(self.sidebar, "＋  Crear evento", expanded=True)
        card.pack(fill="x", pady=6)
        quick_fields = [field for field in EVENT_FIELDS if field[0] != "time"]
        self.quick_entries = widgets.linked_form(
            body, quick_fields, self.new_vars, width=13, on_enter=self.do_create)
        self._quick_placeholders = {
            "id": "Ej. SIS-000042", "magnitude": "Ej. 6.5",
            "depth": "Ej. 10.0 km", "x": "Ej. 120.0 km",
            "y": "Ej. 120.0 km", "station": "Código estación",
        }
        for name, placeholder in self._quick_placeholders.items():
            widgets.set_placeholder(
                self.quick_entries[name], self.new_vars[name], placeholder,
                on_touch=lambda field=name: self._touch_quick_field(field))
        picker, self.apply_utc_value, self.utc_valid, self.date_entry, self.time_entry = widgets.utc_picker(
            body, self.new_vars["time"], format_time(self.ctl.catalog.clock),
            on_change=lambda: self._touch_quick_field("time"))
        picker.grid(row=2 * len(quick_fields), column=0, columnspan=2, sticky="ew", pady=3)
        self.quick_validation = ttk.Label(body, text="", style="Validation.TLabel")
        self.quick_validation.grid(row=2 * len(quick_fields) + 1, column=0, columnspan=2,
                                   sticky="w", padx=3)
        self.quick_submit = ttk.Button(body, text="Crear evento", style="Primary.TButton",
                                       command=self.do_create)
        self.quick_submit.grid(row=2 * len(quick_fields) + 2, column=0, columnspan=2,
                               sticky="ew", padx=3, pady=(5, 2))
        self._validate_quick_event()

        card, body = widgets.collapsible_card(self.sidebar, "✎  Corregir / eliminar")
        card.pack(fill="x", pady=6)
        ttk.Label(body, text="Identificador", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=3, pady=(4, 1))
        fix_id_entry = ttk.Entry(body, textvariable=self.fix_id, width=13)
        fix_id_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=3, pady=2)
        fix_id_entry.bind("<Return>", lambda _event: self.do_correct())
        widgets.linked_form(body, CORRECT_FIELDS, self.fix_vars, width=13,
                            on_enter=self.do_correct, row=2)
        ttk.Label(body, text="Deje vacío lo que no cambia", style="Muted.TLabel").grid(
            row=2 + 2 * len(CORRECT_FIELDS), column=0, columnspan=2,
            sticky="w", padx=3, pady=2)
        actions = ttk.Frame(body, style="Card.TFrame")
        actions.grid(row=3 + 2 * len(CORRECT_FIELDS), column=0, columnspan=2, sticky="ew")
        ttk.Button(actions, text="Corregir…", command=self.do_correct).pack(fill="x", pady=2)
        ttk.Button(actions, text="Eliminar…", command=self.do_delete).pack(fill="x", pady=2)
        ttk.Button(actions, text="Marcar revisado", command=self.do_review).pack(fill="x", pady=2)

        card, body = widgets.collapsible_card(self.sidebar, "⌕  Buscar evento")
        card.pack(fill="x", pady=6)
        self.sidebar_search = tk.StringVar()
        search = ttk.Entry(body, textvariable=self.sidebar_search)
        search.pack(fill="x", pady=3)
        search.bind("<Return>", lambda _event: self._search_sidebar_event())
        ttk.Button(body, text="Abrir detalle", command=self._search_sidebar_event).pack(fill="x")

        card, body = widgets.collapsible_card(self.sidebar, "⚙  Parámetros · W / R / L / T")
        card.pack(fill="x", pady=6)
        for row, name in enumerate(("W", "R", "L", "T")):
            ttk.Label(body, text=name, style="Card.TLabel").grid(row=2 * row, column=0,
                                                                  sticky="w", padx=3, pady=(4, 1))
            ttk.Entry(body, textvariable=self.params[name], width=13).grid(
                row=2 * row + 1, column=0, sticky="ew", padx=3, pady=(0, 3))
        ttk.Button(body, text="Aplicar parámetros", command=self.apply_params).grid(
            row=8, column=0, sticky="ew", padx=3, pady=4)

        card, body = widgets.collapsible_card(self.sidebar, "▣  Archivo / versiones")
        card.pack(fill="x", pady=6)
        ttk.Button(body, text="Abrir archivos y versiones",
                   command=lambda: self.nb.select(6)).pack(fill="x", pady=2)
        ttk.Button(body, text="Histórico y archivo de ramas",
                   command=lambda: self.nb.select(5)).pack(fill="x", pady=2)
        widgets.Tooltip(search, "Busque un evento por SIS-000001 o por su identificador.")
        for name, entry in self.quick_entries.items():
            widgets.Tooltip(entry, self._quick_placeholders[name])

    def _build_inspector(self):
        ttk.Label(self.inspector, text="DETALLE DEL EVENTO", style="Card.TLabel").pack(anchor="w")
        self.detail_values = {}
        detail = ttk.Frame(self.inspector, style="Card.TFrame", padding=6)
        detail.pack(fill="x", pady=(5, 9))
        for row, (name, label) in enumerate((
                ("id", "ID"), ("status", "Estado"), ("priority", "Prioridad"),
                ("magnitude", "Magnitud"), ("depth", "Profundidad"),
                ("location", "Epicentro"), ("time", "Hora UTC"),
                ("revision", "Revisión"), ("tree", "Nodo AVL"))):
            ttk.Label(detail, text=label, style="Muted.TLabel").grid(
                row=row, column=0, sticky="w", padx=3, pady=3)
            value = ttk.Label(detail, text="—", style="Card.TLabel", wraplength=160)
            value.grid(row=row, column=1, sticky="e", padx=3, pady=3)
            self.detail_values[name] = value
        actions = ttk.Frame(detail, style="Card.TFrame")
        actions.grid(row=len(self.detail_values), column=0, columnspan=2, sticky="ew", pady=(5, 3))
        ttk.Button(actions, text="Marcar revisado", command=self.review_selected).pack(
            side="left", expand=True, fill="x", padx=(0, 2))
        ttk.Button(actions, text="Eliminar…", command=self.delete_selected).pack(
            side="left", expand=True, fill="x", padx=(2, 0))
        ttk.Label(detail, text="RECORRIDOS", style="Muted.TLabel").grid(
            row=len(self.detail_values) + 1, column=0, columnspan=2, sticky="w", padx=3, pady=(5, 1))
        self.travs = tk.Text(detail, height=7, wrap="word", font=theme.FONTS["ui"],
                             bg=theme.PALETTE["surface"], fg=theme.PALETTE["text"],
                             relief="flat", highlightthickness=0, borderwidth=0)
        self.travs.grid(row=len(self.detail_values) + 2, column=0, columnspan=2, sticky="ew", padx=3)
        self.travs.configure(state="disabled")
        detail.columnconfigure(1, weight=1)
        ttk.Label(self.inspector, text="EVENTOS ACTIVOS", style="Card.TLabel").pack(
            anchor="w", pady=(3, 2))
        self.active_filter = tk.StringVar()
        search = ttk.Entry(self.inspector, textvariable=self.active_filter)
        search.pack(fill="x", pady=(0, 4))
        search.bind("<KeyRelease>", lambda _event: self._refresh_active_events())
        frame, self.active_table = table(
            self.inspector, [("id", 92), ("M", 42), ("P", 28), ("estado", 75)], height=16)
        frame.pack(fill="both", expand=True)
        self.active_table.bind("<<TreeviewSelect>>", self._pick_active_event)
        self._style_text_box(self.travs)

    @staticmethod
    def _style_text_box(box):
        box.configure(highlightthickness=0, relief="flat", borderwidth=0)

    def _refresh_inspector(self):
        values = {key: "—" for key in self.detail_values}
        if self.selected is not None:
            out = self.ctl.describe(self.selected)
            if out.ok:
                info = out.data
                event = info["event"]
                values.update({
                    "id": sid(event.event_id),
                    "status": info["status"],
                    "priority": f"{event.priority} · {('alta' if event.priority == 3 else 'media' if event.priority == 2 else 'baja')}",
                    "magnitude": f"{event.magnitude:.1f}",
                    "depth": f"{event.depth:.1f} km",
                    "location": f"{event.x:.1f}, {event.y:.1f} km",
                    "time": format_time(event.time),
                    "revision": str(event.revision),
                    "tree": (f"h {info['height']} · fb {info['balance']:+d}"
                             if info["status"] == "activo" else "Fuera del AVL"),
                })
        for key, value in values.items():
            self.detail_values[key].configure(text=value)

    def _refresh_active_events(self):
        if not hasattr(self, "active_table"):
            return
        needle = self.active_filter.get().strip().casefold()
        rows = []
        for row in self.ctl.event_rows():
            if row[1] != "activo":
                continue
            if needle and needle not in str(row[0]).casefold() and needle not in str(row[3]).casefold():
                continue
            rows.append((row[0], f"{float(row[3]):.1f}", row[2], row[9]))
        fill(self.active_table, rows)

    def _pick_active_event(self, _event):
        picked = self.active_table.selection()
        if picked:
            values = self.active_table.item(picked[0], "values")
            self.select(int(str(values[0]).replace("SIS-", "")))

    def _search_sidebar_event(self):
        out = self.ctl.describe(self.sidebar_search.get().strip())
        self.say(out, popup=not out.ok)
        if out.ok:
            self.select(out.data["event"].event_id)

    def _validate_quick_event(self):
        if not hasattr(self, "quick_entries"):
            return
        values = {name: variable.get().strip() for name, variable in self.new_vars.items()}
        for name, placeholder in self._quick_placeholders.items():
            if values[name] == placeholder:
                values[name] = ""
        errors = {}
        try:
            parse_id(values["id"])
        except ValidationError as error:
            errors["id"] = str(error)
        for name, label, low, high in (
                ("magnitude", "la magnitud", -2.0, 10.0),
                ("depth", "la profundidad", 0.0, 700.0),
                ("x", "la coordenada x", 0.0, 1000.0),
                ("y", "la coordenada y", 0.0, 1000.0)):
            try:
                parse_decimal(values[name], label, low, high)
            except ValidationError as error:
                errors[name] = str(error)
        if not self.utc_valid["value"]:
            errors["time"] = "Use AAAA-MM-DD y HH:MM válidos."
        else:
            try:
                moment = parse_time(values["time"])
                if moment > self.ctl.catalog.clock:
                    errors["time"] = "La fecha supera el reloj simulado."
            except ValidationError as error:
                errors["time"] = str(error)
        try:
            self.ctl.catalog.check_station(values["station"])
        except ValidationError as error:
            errors["station"] = str(error)
        for name, entry in self.quick_entries.items():
            if name in errors and name in self._quick_touched:
                entry.configure(style="Invalid.TEntry")
            elif name not in self._quick_touched and name in self._quick_placeholders:
                entry.configure(style="Placeholder.TEntry")
            else:
                entry.configure(style="TEntry")
        if "time" in errors and "time" in self._quick_touched:
            self.date_entry.configure(style="Invalid.TEntry")
            self.time_entry.configure(style="Invalid.TEntry")
        if errors:
            visible_error = next((errors[name] for name in self._quick_touched if name in errors), "")
            self.quick_validation.configure(text=visible_error)
            self.quick_submit.configure(state="disabled")
        else:
            self.quick_validation.configure(text="")
            self.quick_submit.configure(state="normal")

    def _touch_quick_field(self, name):
        self._quick_touched.add(name)
        self._validate_quick_event()

    def _blink_stress(self):
        if self.ctl.catalog.avl.stress:
            self._stress_flash = not self._stress_flash
            self.mode_badge.configure(style="ModeStress.TLabel" if self._stress_flash else
                                      "ModeNormal.TLabel")
        else:
            self._stress_flash = False
            self.mode_badge.configure(style="ModeNormal.TLabel")
        self.root.after(550, self._blink_stress)

    def select(self, event_id):
        self.selected = event_id
        self.fix_id.set(sid(event_id))
        self.refresh()

    # ---------- tab: AVL ----------

    def _tab_tree(self, tab):
        ttk.Label(tab, text="Árbol AVL", style="Brand.TLabel").pack(anchor="w", padx=8, pady=(7, 0))
        top = ttk.Frame(tab, padding=(7, 6))
        top.pack(fill="x")
        self.depth_var = tk.StringVar(value="12")
        ttk.Label(top, text="Niveles visibles").pack(side="left", padx=4)
        ttk.Spinbox(top, from_=1, to=60, width=4, textvariable=self.depth_var,
                    command=self.refresh).pack(side="left")
        ttk.Button(top, text="Ajustar a pantalla", command=self._fit_tree).pack(side="left", padx=5)
        ttk.Button(top, text="−", command=lambda: self.tree_nav.zoom_center(0.88)).pack(side="left")
        ttk.Button(top, text="+", command=lambda: self.tree_nav.zoom_center(1.14)).pack(side="left")
        self.legend = tk.Canvas(top, width=570, height=26, bg=theme.PALETTE["background"],
                                highlightthickness=0)
        self.legend.pack(side="left", padx=8)
        body = ttk.Panedwindow(tab, orient="horizontal")
        body.pack(fill="both", expand=True)
        left, self.tree_canvas = canvas_with_bars(body, 820, 420)
        self.tree_nav = tree_canvas.TreeCanvasNavigator(self.tree_canvas)
        self._tree_fit_pending = False
        body.add(left, weight=1)
        self.tree_canvas.bind("<ButtonRelease-1>", self._click_tree, add="+")

        def refresh():
            try:
                depth = max(1, int(self.depth_var.get()))
            except ValueError:
                depth = 12
            view = self.ctl.tree_view(depth)
            self.legend.delete("all")
            drawing.draw_legend(self.legend)
            signature = {eid: (node.left, node.right)
                         for eid, node in view["layout"].nodes.items()}
            rotation_stats = tuple(self.ctl.catalog.avl.stats[key]
                                   for key in ("LL", "RR", "LR", "RL"))
            if (self._rotation_stats is not None and
                    sum(rotation_stats) > sum(self._rotation_stats)):
                self._rotated_nodes = {
                    eid for eid in signature.keys() & self._tree_structure.keys()
                    if signature[eid] != self._tree_structure[eid]
                }
                if self._rotation_after is not None:
                    self.root.after_cancel(self._rotation_after)
                self._rotation_after = self.root.after(1000, self._clear_rotation_highlight)
            self._tree_structure = signature
            self._rotation_stats = rotation_stats
            self.tree_hits = drawing.draw_tree(
                self.tree_canvas, view["layout"], view["events"], view["costly"],
                view["imbalanced"], self.selected,
                rotated=self._rotated_nodes)
            if self._rotated_nodes and self._rotation_animation is None and hasattr(self.root, "_w"):
                self._rotation_frame = 0
                self._animate_rotations()
            self.tree_nav.apply_after_redraw()
            if not self._tree_fit_pending:
                self._tree_fit_pending = True
                self.root.after_idle(self.tree_nav.fit)
            set_text(self.travs, self.ctl.traversal_text())
        return refresh

    def _fit_tree(self):
        self.tree_nav.fit()

    def _clear_rotation_highlight(self):
        self._rotated_nodes.clear()
        self._rotation_after = None
        self.refresh()

    def _animate_rotations(self):
        widths = (4, 5, 6, 5, 4, 3, 4, 5, 4)
        if self._rotation_frame >= len(widths) or not self._rotated_nodes:
            self._rotation_animation = None
            return
        self.tree_canvas.itemconfigure("rotation-highlight",
                                       outline=theme.PALETTE["warning"],
                                       width=widths[self._rotation_frame])
        self._rotation_frame += 1
        self._rotation_animation = self.root.after(110, self._animate_rotations)

    def _click_tree(self, event):
        if self.tree_nav.dragged:
            self.tree_nav.dragged = False
            return
        x, y = self.tree_canvas.canvasx(event.x), self.tree_canvas.canvasy(event.y)
        x, y = self.tree_nav.to_world(x, y)
        hit = drawing.hit_node(self.tree_hits, x, y)
        if hit is not None:
            self.select(hit)

    def _need_selection(self):
        if self.selected is None:
            self.say(self._ok("Seleccione primero un evento."), popup=False)
            messagebox.showinfo("SismoLab AVL", "Seleccione primero un evento.")
            return False
        return True

    def review_selected(self):
        if self._need_selection():
            self.act(self.ctl.review(self.selected))

    def delete_selected(self):
        if self._need_selection() and self.confirm("Eliminar evento", self.ctl.preview_delete(self.selected)):
            self.act(self.ctl.delete(self.selected))

    # ---------- tab: AVL vs BST ----------

    def _tab_compare(self, tab):
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Label(top, text="Orden de inserción del BST:").pack(side="left", padx=4)
        self.order_var = tk.StringVar(value="ascending")
        ttk.Combobox(top, textvariable=self.order_var, width=12, state="readonly",
                     values=["original", "ascending", "descending", "random", "file"]
                     ).pack(side="left")
        ttk.Button(top, text="Comparar", command=self.refresh).pack(side="left", padx=6)
        ttk.Label(top, text="(original = por id, file = orden del último archivo de inserciones)"
                  ).pack(side="left")
        frame, self.cmp_stats = text_box(tab, height=5, width=140)
        frame.pack(fill="x")
        panes = ttk.Panedwindow(tab, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        right = ttk.Frame(panes)
        ttk.Label(left, text="AVL balanceado", style="Card.TLabel").pack(anchor="w", padx=6, pady=4)
        ttk.Label(right, text="BST sin balanceo", style="Card.TLabel").pack(anchor="w", padx=6, pady=4)
        canvas_frame, self.cmp_avl = canvas_with_bars(left, 600, 380)
        canvas_frame.pack(fill="both", expand=True)
        canvas_frame, self.cmp_bst = canvas_with_bars(right, 600, 380)
        canvas_frame.pack(fill="both", expand=True)
        panes.add(left, weight=1)
        panes.add(right, weight=1)

        def refresh():
            out = self.ctl.comparison_view(self.order_var.get())
            if not out.ok:
                set_text(self.cmp_stats, out.message)
                self.cmp_avl.delete("all")
                self.cmp_bst.delete("all")
                return
            data = out.data
            a, b = data["stats"]["avl"], data["stats"]["bst"]
            row = lambda n, s: (f"{n:4s} raíz={s['root']}  altura={s['height']}  prof. máx={s['max_depth']}  "
                                f"hojas={s['leaves']}  comparaciones al buscar las {data['n']} claves="
                                f"{s['search_comparisons']}  promedio={s['search_average']:.2f}")
            set_text(self.cmp_stats, row("AVL", a) + "\n" + row("BST", b))
            empty = {}
            drawing.draw_tree(self.cmp_avl, data["avl"], empty, title="AVL (con balanceo)")
            drawing.draw_tree(self.cmp_bst, data["bst"], empty, title="BST (sin balanceo)")
        return refresh

    # ---------- tab: plane ----------

    def _tab_plane(self, tab):
        body = ttk.Panedwindow(tab, orient="horizontal")
        body.pack(fill="both", expand=True)
        left, self.plane_canvas = canvas_with_bars(body, 700, 700)
        right = ttk.Frame(body)
        body.add(left, weight=4)
        body.add(right, weight=1)
        legend = ("Cómo leer el plano (0-1000 km)\n\n"
                  "• Rectángulo amarillo: zona poblada; gris: no poblada.\n"
                  "• Círculo lleno: evento activo; color = prioridad\n  (rojo alta, naranja media, verde baja).\n"
                  "• Tamaño del círculo: crece con la magnitud.\n"
                  "• Anillo morado grueso: acceso costoso.\n"
                  "• Círculo gris punteado: evento archivado.\n"
                  "• Línea punteada: evento -> su referencia.\n"
                  "• Número: identificador. Clic para seleccionar.")
        ttk.Label(right, text=legend, justify="left").pack(anchor="w", padx=4)
        frame, self.plane_info = text_box(right, height=12, width=38)
        frame.pack(fill="both", expand=True)
        self.plane_canvas.bind("<Button-1>", self._click_plane)

        def refresh():
            self.plane_hits = drawing.draw_plane(self.plane_canvas, self.ctl.plane_view(),
                                                 selected=self.selected)
            if self.selected is None:
                set_text(self.plane_info, "Seleccione un evento.")
            else:
                set_text(self.plane_info, self.ctl.describe(self.selected).message)
        return refresh

    def _click_plane(self, event):
        x, y = self.plane_canvas.canvasx(event.x), self.plane_canvas.canvasy(event.y)
        hit = drawing.hit_point(self.plane_hits, x, y)
        if hit is not None:
            self.select(hit)

    # ---------- tab: events ----------

    def _tab_events(self, tab):
        left = ttk.Frame(tab)
        left.pack(fill="both", expand=True, padx=7, pady=7)
        ttk.Label(left, text="Catálogo completo · seleccione una fila para abrir el detalle",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 5))
        frame, self.ev_table = table(left, EVENT_COLUMNS, height=22)
        frame.pack(fill="both", expand=True)
        self.ev_table.bind("<<TreeviewSelect>>", self._pick_event_row)

        def refresh():
            fill(self.ev_table, self.ctl.event_rows())
        return refresh

    def _pick_event_row(self, _event):
        picked = self.ev_table.selection()
        if picked:
            text = self.ev_table.item(picked[0], "values")[0]
            try:
                event_id = int(str(text).replace("SIS-", ""))
            except ValueError:
                return
            self.select(event_id)

    def do_create(self):
        v = {k: var.get().strip() for k, var in self.new_vars.items()}
        out = self.ctl.create(v["id"], v["magnitude"], v["depth"], v["x"], v["y"], v["time"],
                              v["station"])
        if out.ok:
            self.selected = out.data
        self.act(out)

    def _fix_changes(self):
        return {k: var.get().strip() for k, var in self.fix_vars.items() if var.get().strip()}

    def do_correct(self):
        changes = self._fix_changes()
        if not changes:
            self.say(self._ok("Escriba al menos un valor a corregir."), popup=True)
            return
        if self.confirm("Corregir evento", self.ctl.preview_correction(self.fix_id.get(), changes)):
            self.act(self.ctl.correct(self.fix_id.get(), changes))

    def do_delete(self):
        if self.confirm("Eliminar evento", self.ctl.preview_delete(self.fix_id.get())):
            self.act(self.ctl.delete(self.fix_id.get()))

    def do_review(self):
        self.act(self.ctl.review(self.fix_id.get()))

    # ---------- tab: queue ----------

    def _tab_queue(self, tab):
        top = ttk.Frame(tab)
        top.pack(fill="both", expand=True)
        right = ttk.LabelFrame(top, text="Preparar ráfaga")
        right.pack(side="right", fill="y", padx=6)
        left = ttk.Frame(top)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Cola FIFO (el primero de la lista se procesa primero)").pack(anchor="w")
        frame, self.q_table = table(left, [("pos", 35), ("estación", 70), ("evento", 60), ("rev", 35),
                                            ("M", 40), ("H", 45), ("x", 50), ("y", 50), ("hora", 135)], 9)
        frame.pack(fill="both", expand=True)
        controls = ttk.Frame(left)
        controls.pack(fill="x", pady=3)
        ttk.Button(controls, text="Paso (1 reporte)", command=self.do_step).pack(side="left", padx=2)
        ttk.Button(controls, text="Continuo", command=self.start_continuous).pack(side="left", padx=2)
        ttk.Button(controls, text="Pausa", command=self.stop_continuous).pack(side="left", padx=2)
        ttk.Label(controls, text="Pausa entre pasos (ms):").pack(side="left", padx=4)
        self.delay = tk.StringVar(value="700")
        ttk.Entry(controls, textvariable=self.delay, width=6).pack(side="left")
        ttk.Label(left, text="Resultados de los pasos").pack(anchor="w")
        frame, self.q_results = table(left, [("estación", 70), ("evento", 80), ("rev", 35),
                                              ("decisión", 80), ("giros", 160), ("explicación", 420)], 9)
        frame.pack(fill="both", expand=True)
        defaults = {"revision": "1", "time": format_time(self.ctl.catalog.clock)}
        self.burst_vars = form(right, BURST_FIELDS, defaults=defaults, width=20,
                               on_enter=self.add_draft)
        row = 2 * len(BURST_FIELDS)
        ttk.Button(right, text="Agregar al borrador", command=self.add_draft).grid(row=row, column=0,
                                                                                  columnspan=2, pady=2)
        self.draft_label = ttk.Label(right, text="Borrador: 0 reporte(s)")
        self.draft_label.grid(row=row + 1, column=0, columnspan=2)
        ttk.Button(right, text="Enviar borrador a la cola", command=self.send_draft
                   ).grid(row=row + 2, column=0, columnspan=2, pady=2)
        ttk.Button(right, text="Cargar ráfaga desde archivo…", command=self.load_burst
                   ).grid(row=row + 3, column=0, columnspan=2, pady=2)

        def refresh():
            fill(self.q_table, self.ctl.queue_rows())
            self.draft_label.configure(text=f"Borrador: {len(self.draft)} reporte(s)")
        return refresh

    def add_draft(self):
        row = {k: var.get().strip() for k, var in self.burst_vars.items()}
        for key in ("event_id", "revision"):
            if row[key].isdigit():
                row[key] = int(row[key])
        self.draft.append(row)
        self.refresh()

    def send_draft(self):
        if not self.draft:
            self.say(self._ok("El borrador está vacío."), popup=True)
            return
        if self.act(self.ctl.enqueue(self.draft)):
            self.draft = []
            self.refresh()

    def load_burst(self):
        path = filedialog.askopenfilename(title="Ráfaga de reportes", filetypes=JSON_TYPES)
        if path:
            self.act(self.ctl.import_reports(path))

    def do_step(self, continuous=False):
        out = self.ctl.step(continuous)
        if out.ok:
            r, res = out.data.report, out.data
            rot = ", ".join(f"{k}×{v}" for k, v in res.cases.items() if v)
            self.q_results.insert("", "end", values=(
                r.station, sid(res.event_id) if res.event_id else r.event_id, r.revision, res.decision,
                f"{res.rotations} giro(s) {rot}", res.message))
        self.act(out, popup=not continuous)
        return out.ok

    def start_continuous(self):
        if self.running:
            self.say(self._ok("El procesamiento continuo ya está en marcha."))
            return
        self.running = True
        self.say(self._ok("Procesamiento continuo iniciado (un reporte por tick)."))
        self._tick()

    def stop_continuous(self):
        self.running = False
        if self._queue_after is not None:
            self.root.after_cancel(self._queue_after)
            self._queue_after = None
        self.say(self._ok("Procesamiento continuo en pausa."))

    def _tick(self):
        if not self.running:
            return
        self._queue_after = None
        if not self.do_step(continuous=True):
            self.running = False              # empty queue or recovery pause: stop, the log says why
            return
        if self.ctl.queue.is_empty():
            self.running = False
            return
        try:
            delay = max(50, int(self.delay.get()))
        except ValueError:
            delay = 700
        self._queue_after = self.root.after(delay, self._tick)

    # ---------- tab: history ----------

    def _tab_history(self, tab):
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Button(top, text="Vista previa: archivar rama antigua", command=self.preview_archive
                   ).pack(side="left", padx=3, pady=3)
        ttk.Button(top, text="Archivar rama…", command=self.do_archive).pack(side="left", padx=3)
        frame, self.arch_info = text_box(tab, height=5, width=140)
        frame.pack(fill="x")
        ttk.Label(tab, text="Histórico (archivados) y retirados (eliminados)").pack(anchor="w")
        frame, self.hist_table = table(tab, EVENT_COLUMNS, height=8)
        frame.pack(fill="both", expand=True)
        ttk.Label(tab, text="Registro de acciones deshacibles (primera = más antigua)").pack(anchor="w")
        frame, self.log_table = table(tab, [("n", 35), ("acción", 300), ("resumen", 250),
                                             ("métricas que cambió", 500)], height=8)
        frame.pack(fill="both", expand=True)

        def refresh():
            rows = [r for r in self.ctl.event_rows() if r[1] != "activo"]
            fill(self.hist_table, rows)
            fill(self.log_table, self.ctl.history_rows())
        return refresh

    def preview_archive(self):
        out = self.ctl.preview_archive()
        set_text(self.arch_info, out.message)
        self.say(out)

    def do_archive(self):
        out = self.ctl.preview_archive()
        set_text(self.arch_info, out.message)
        if self.confirm("Archivar rama", out):
            self.act(self.ctl.archive())

    # ---------- tab: files and versions ----------

    def _tab_files(self, tab):
        files = ttk.LabelFrame(tab, text="Archivos JSON (elija la ruta con el explorador)")
        files.pack(fill="x", padx=4, pady=4)
        for text, command in (("Guardar estado completo…", self.save_state),
                              ("Cargar por topología…", self.load_topology),
                              ("Cargar por inserciones…", self.load_insertions)):
            ttk.Button(files, text=text, command=command).pack(side="left", padx=4, pady=4)
        box = ttk.LabelFrame(tab, text="Versiones con nombre")
        box.pack(fill="both", expand=True, padx=4, pady=4)
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.ver_name = tk.StringVar()
        ttk.Label(row, text="Nombre:").pack(side="left", padx=3)
        ttk.Entry(row, textvariable=self.ver_name, width=24).pack(side="left")
        ttk.Button(row, text="Guardar versión", command=self.save_version).pack(side="left", padx=4)
        ttk.Button(row, text="Restaurar seleccionada", command=self.restore_version).pack(side="left", padx=4)
        ttk.Button(row, text="Carpeta…", command=self.pick_folder).pack(side="left", padx=4)
        ttk.Label(row, textvariable=self.versions_folder).pack(side="left", padx=4)
        frame, self.ver_table = table(box, [("nombre", 260), ("reloj", 160), ("eventos activos", 120)], 12)
        frame.pack(fill="both", expand=True)
        self.ver_table.bind("<<TreeviewSelect>>", self._pick_version)

        def refresh():
            fill(self.ver_table, [(v["name"], v["clock"], v["active"])
                                  for v in self.ctl.versions(self.versions_folder.get())])
        return refresh

    def save_state(self):
        path = filedialog.asksaveasfilename(title="Guardar estado", defaultextension=".json",
                                            filetypes=JSON_TYPES)
        if path:
            self.act(self.ctl.export_state(path))

    def load_topology(self):
        path = filedialog.askopenfilename(title="Cargar por topología", filetypes=JSON_TYPES)
        if path:
            self.act(self.ctl.import_topology(path))

    def load_insertions(self):
        path = filedialog.askopenfilename(title="Cargar por inserciones", filetypes=JSON_TYPES)
        if path:
            if self.act(self.ctl.import_insertions(path)):
                self.order_var.set("file")
                self.nb.select(1)

    def pick_folder(self):
        folder = filedialog.askdirectory(title="Carpeta de versiones")
        if folder:
            self.versions_folder.set(folder)
            self.refresh()

    def save_version(self):
        self.act(self.ctl.save_version(self.ver_name.get(), self.versions_folder.get()))

    def _pick_version(self, _event):
        picked = self.ver_table.selection()
        if picked:
            self.ver_name.set(self.ver_table.item(picked[0], "values")[0])

    def restore_version(self):
        self.act(self.ctl.restore_version(self.ver_name.get(), self.versions_folder.get()))

    # ---------- tab: audit ----------

    def _tab_audit(self, tab):
        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Button(top, text="Verificar estructura", command=self.run_audit).pack(side="left", padx=4, pady=4)
        frame, self.audit_box = text_box(tab, height=14, width=140)
        frame.pack(fill="both", expand=True)
        ttk.Label(tab, text="Indicadores").pack(anchor="w")
        frame, self.ind_box = text_box(tab, height=9, width=140)
        frame.pack(fill="x")

        def refresh():
            set_text(self.ind_box, self.ctl.indicators_text() + "\n\n" + self.ctl.traversal_text())
        return refresh

    def _tab_indicators(self, tab):
        ttk.Label(tab, text="Indicadores operativos del catálogo", style="Brand.TLabel").pack(
            anchor="w", padx=10, pady=10)
        cards = ttk.Frame(tab)
        cards.pack(fill="x", padx=7)
        self.indicator_cards = {}
        for column, (name, label) in enumerate((
                ("active", "Activos"), ("archived", "Archivados"), ("deleted", "Eliminados"),
                ("queue", "Cola FIFO"), ("pending", "Pendientes"), ("costly_access", "Costosos"),
                ("height", "Altura AVL"), ("leaves", "Hojas"))):
            card, value = widgets.metric_card(cards, label)
            card.grid(row=0, column=column, sticky="ew", padx=3, pady=3)
            cards.columnconfigure(column, weight=1)
            self.indicator_cards[name] = value
        frame, self.indicator_report = text_box(tab, height=18, width=100)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        def refresh():
            data = indicators(self.ctl.catalog, self.ctl.queue)
            for key, value in self.indicator_cards.items():
                value.configure(text=str(data[key]))
            set_text(self.indicator_report, self.ctl.indicators_text())
        return refresh

    def run_audit(self):
        out = self.ctl.audit()
        set_text(self.audit_box, out.message)
        self.say(out)

    # ---------- tab: queries ----------

    def _tab_queries(self, tab):
        grid = ttk.Frame(tab)
        grid.pack(fill="x", padx=4, pady=4)
        self.q = {n: tk.StringVar(value=v) for n, v in (
            ("k", "5"), ("low", "4.0"), ("high", "6.0"), ("depth", "30"),
            ("start", "2026-09-01T00:00:00Z"), ("end", format_time(self.ctl.catalog.clock)), ("id", ""))}
        rows = [("Primeros k pendientes", [("k", "k")], "top"),
                ("Rango de magnitud", [("low", "mín"), ("high", "máx")], "magnitude"),
                ("Poco profundos en fechas", [("depth", "H máx"), ("start", "desde"), ("end", "hasta")], "dates"),
                ("Asociaciones de un evento", [("id", "id")], "associations"),
                ("Acceso costoso", [], "costly")]
        for r, (title, fields, name) in enumerate(rows):
            ttk.Label(grid, text=title, width=26).grid(row=r, column=0, sticky="w")
            for c, (var, label) in enumerate(fields, start=1):
                sub = ttk.Frame(grid)
                sub.grid(row=r, column=c, padx=3)
                ttk.Label(sub, text=label).grid(row=0, column=0, sticky="w")
                ttk.Entry(sub, textvariable=self.q[var],
                          width=22 if var in ("start", "end") else 8
                          ).grid(row=1, column=0, sticky="ew")
            ttk.Button(grid, text="Consultar", command=lambda n=name: self.run_query(n)
                       ).grid(row=r, column=5, padx=6)
        frame, self.query_box = text_box(tab, height=22, width=140)
        frame.pack(fill="both", expand=True, padx=4)
        return lambda: None

    def run_query(self, name):
        args = {k: v.get().strip() for k, v in self.q.items()}
        out = self.ctl.query(name, **args)
        set_text(self.query_box, out.message)
        if not out.ok:
            self.say(out, popup=True)


def main():
    from ui.main_window import launch

    launch()


if __name__ == "__main__":
    main()

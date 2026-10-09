"""SismoLab AVL - Tkinter interface.

Only presentation: every action goes through ui.controller.Controller (which
uses Scenario). No widget class is subclassed, so the file stays easy to read.
Run:  python -m ui.app     (or: python main.py)
"""

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from domain.models import format_time
from services.persistence import DEFAULT_VERSIONS_DIR
from ui import drawing
from ui.controller import Controller, Outcome, sid

JSON_TYPES = [("Archivos JSON", "*.json"), ("Todos los archivos", "*.*")]
BURST_FIELDS = [("station", "Estación"), ("event_id", "Evento (id)"), ("revision", "Revisión"),
                ("magnitude", "Magnitud"), ("depth", "Prof. H (km)"), ("x", "x (km)"),
                ("y", "y (km)"), ("time", "Hora ISO UTC")]
EVENT_FIELDS = [("id", "Identificador"), ("magnitude", "Magnitud"), ("depth", "Profundidad H (km)"),
                ("x", "x (km)"), ("y", "y (km)"), ("time", "Hora ISO UTC"), ("station", "Estación")]
CORRECT_FIELDS = [("magnitude", "Magnitud"), ("depth", "Profundidad H"), ("x", "x"), ("y", "y"),
                  ("time", "Hora ISO UTC")]
EVENT_COLUMNS = [("id", 90), ("estado", 70), ("P", 30), ("M", 40), ("H", 45), ("x", 50), ("y", 50),
                 ("hora", 135), ("rev", 35), ("atención", 70), ("prof. nodo", 70),
                 ("costoso", 55), ("referencia", 90)]


# ---------- small widget helpers ----------

def form(parent, fields, row=0, defaults=None, width=18):
    """Grid of label + entry. Returns {name: StringVar}."""
    variables = {}
    for offset, (name, label) in enumerate(fields):
        ttk.Label(parent, text=label).grid(row=row + offset, column=0, sticky="w", padx=3, pady=1)
        var = tk.StringVar(value=(defaults or {}).get(name, ""))
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row + offset, column=1, padx=3, pady=1)
        variables[name] = var
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
    box = tk.Text(frame, height=height, width=width, wrap="word", font=("Consolas", 9))
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
    canvas = tk.Canvas(frame, width=width, height=height, bg="white", highlightthickness=0)
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
        self.versions_folder = tk.StringVar(value=DEFAULT_VERSIONS_DIR)
        self.tab_refresh = {}
        self.tree_hits, self.plane_hits, self.draft = [], [], []
        root.title("SismoLab AVL")
        root.geometry("1280x800")
        self._build_toolbar()
        self._build_notebook()
        self._build_log()
        self.say(self._ok("Bienvenida a SismoLab AVL. Cargue un archivo o cree eventos."))
        self.refresh()

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
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=4, pady=3)
        ttk.Button(bar, text="Deshacer", command=lambda: self.act(self.ctl.undo())).pack(side="left", padx=2)
        self.stress_btn = ttk.Button(bar, text="Activar modo estrés", command=self.toggle_stress)
        self.stress_btn.pack(side="left", padx=2)
        ttk.Button(bar, text="Recuperación global", command=lambda: self.act(self.ctl.recover())
                   ).pack(side="left", padx=2)
        ttk.Button(bar, text="Reanudar cola", command=lambda: self.act(self.ctl.resume())
                   ).pack(side="left", padx=2)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        self.hours = tk.StringVar(value="24")
        ttk.Label(bar, text="Reloj +h").pack(side="left")
        ttk.Entry(bar, textvariable=self.hours, width=5).pack(side="left", padx=2)
        ttk.Button(bar, text="Avanzar", command=lambda: self.act(self.ctl.advance_clock(self.hours.get()))
                   ).pack(side="left", padx=2)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
        self.params = {}
        for name in ("W", "R", "L", "T"):
            ttk.Label(bar, text=name).pack(side="left")
            self.params[name] = tk.StringVar()
            ttk.Entry(bar, textvariable=self.params[name], width=5).pack(side="left", padx=2)
        ttk.Button(bar, text="Aplicar", command=self.apply_params).pack(side="left", padx=2)
        self.clock_label = ttk.Label(bar, text="")
        self.clock_label.pack(side="right", padx=6)
        self.banner = tk.Label(self.root, text="", fg="white", bg="#b71c1c", font=("Segoe UI", 10, "bold"))

    def _build_log(self):
        ttk.Label(self.root, text="¿Qué ocurrió y por qué?").pack(anchor="w", padx=6)
        frame, self.log = text_box(self.root, height=6, width=150)
        self.log.tag_configure("error", foreground="#b71c1c")
        self.log.tag_configure("ok", foreground="#1b5e20")
        frame.pack(fill="x", padx=4, pady=3)

    def toggle_stress(self):
        self.act(self.ctl.set_stress(not self.ctl.catalog.avl.stress))

    def apply_params(self):
        self.act(self.ctl.set_parameters(*(self.params[n].get() for n in ("W", "R", "L", "T"))))

    # ---------- notebook ----------

    def _build_notebook(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=4, pady=3)
        builders = [("Árbol AVL", self._tab_tree), ("Comparación BST", self._tab_compare),
                    ("Plano geográfico", self._tab_plane), ("Eventos", self._tab_events),
                    ("Cola", self._tab_queue), ("Histórico", self._tab_history),
                    ("Archivos y versiones", self._tab_files), ("Auditoría", self._tab_audit),
                    ("Consultas", self._tab_queries)]
        self.tab_names = []
        for name, build in builders:
            frame = ttk.Frame(self.nb)
            self.nb.add(frame, text=name)
            self.tab_refresh[name] = build(frame)
            self.tab_names.append(name)
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self.refresh())

    def refresh(self):
        c = self.ctl.catalog
        self.stress_btn.configure(text="Volver a modo normal" if c.avl.stress else "Activar modo estrés")
        self.clock_label.configure(text=f"Reloj: {format_time(c.clock)}   Cola: {len(self.ctl.queue)}"
                                        f"{'   (en pausa)' if self.ctl.sc.paused else ''}")
        for name, value in (("W", c.W), ("R", c.R), ("L", c.L), ("T", c.T)):
            self.params[name].set(str(value))
        view_banner = self.ctl.tree_view(1)["banner"]
        if view_banner:
            self.banner.configure(text=view_banner)
            self.banner.pack(fill="x", padx=4, before=self.nb)
        else:
            self.banner.pack_forget()
        index = self.nb.index(self.nb.select())
        refresher = self.tab_refresh.get(self.tab_names[index]) if self.tab_names else None
        if refresher:
            refresher()

    def select(self, event_id):
        self.selected = event_id
        self.refresh()

    # ---------- tab: AVL ----------

    def _tab_tree(self, tab):
        top = ttk.Frame(tab)
        top.pack(fill="x")
        self.depth_var = tk.StringVar(value="12")
        ttk.Label(top, text="Niveles visibles:").pack(side="left", padx=4)
        ttk.Spinbox(top, from_=1, to=60, width=4, textvariable=self.depth_var,
                    command=self.refresh).pack(side="left")
        ttk.Button(top, text="Redibujar", command=self.refresh).pack(side="left", padx=6)
        self.legend = tk.Canvas(top, width=640, height=26, bg="white", highlightthickness=0)
        self.legend.pack(side="left", padx=8)
        body = ttk.Panedwindow(tab, orient="horizontal")
        body.pack(fill="both", expand=True)
        left, self.tree_canvas = canvas_with_bars(body, 820, 420)
        right = ttk.Frame(body)
        body.add(left, weight=4)
        body.add(right, weight=1)
        ttk.Label(right, text="Nodo seleccionado (clic en el árbol)").pack(anchor="w")
        frame, self.node_info = text_box(right, height=14, width=38)
        frame.pack(fill="both", expand=True)
        row = ttk.Frame(right)
        row.pack(fill="x", pady=3)
        ttk.Button(row, text="Marcar revisado", command=self.review_selected).pack(side="left", padx=2)
        ttk.Button(row, text="Eliminar…", command=self.delete_selected).pack(side="left", padx=2)
        ttk.Label(right, text="Recorridos").pack(anchor="w")
        frame, self.travs = text_box(right, height=7, width=38)
        frame.pack(fill="x")
        self.tree_canvas.bind("<Button-1>", self._click_tree)

        def refresh():
            try:
                depth = max(1, int(self.depth_var.get()))
            except ValueError:
                depth = 12
            view = self.ctl.tree_view(depth)
            self.legend.delete("all")
            drawing.draw_legend(self.legend)
            self.tree_hits = drawing.draw_tree(
                self.tree_canvas, view["layout"], view["events"], view["costly"],
                view["imbalanced"], self.selected,
                title="AVL activo" + ("  (MODO ESTRÉS)" if view["stress"] else ""))
            self._show_node_info()
            set_text(self.travs, self.ctl.traversal_text())
        return refresh

    def _click_tree(self, event):
        x, y = self.tree_canvas.canvasx(event.x), self.tree_canvas.canvasy(event.y)
        hit = drawing.hit_node(self.tree_hits, x, y)
        if hit is not None:
            self.select(hit)

    def _show_node_info(self):
        if self.selected is None:
            set_text(self.node_info, "Seleccione un nodo.")
            return
        out = self.ctl.describe(self.selected)
        set_text(self.node_info, out.message)

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
        left, self.cmp_avl = canvas_with_bars(panes, 600, 380)
        right, self.cmp_bst = canvas_with_bars(panes, 600, 380)
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
        left.pack(side="left", fill="both", expand=True)
        frame, self.ev_table = table(left, EVENT_COLUMNS, height=22)
        frame.pack(fill="both", expand=True)
        self.ev_table.bind("<<TreeviewSelect>>", self._pick_event_row)
        right = ttk.Frame(tab)
        right.pack(side="right", fill="y", padx=6)
        box = ttk.LabelFrame(right, text="Alta de evento")
        box.pack(fill="x", pady=3)
        defaults = {"station": "", "time": format_time(self.ctl.catalog.clock)}
        self.new_vars = form(box, EVENT_FIELDS, defaults=defaults)
        ttk.Button(box, text="Crear evento", command=self.do_create).grid(row=len(EVENT_FIELDS), column=0,
                                                                         columnspan=2, pady=3)
        box2 = ttk.LabelFrame(right, text="Corrección / eliminación (use la fila seleccionada)")
        box2.pack(fill="x", pady=3)
        self.fix_id = tk.StringVar()
        ttk.Label(box2, text="Evento").grid(row=0, column=0, sticky="w", padx=3)
        ttk.Entry(box2, textvariable=self.fix_id, width=18).grid(row=0, column=1, padx=3)
        self.fix_vars = form(box2, CORRECT_FIELDS, row=1)
        ttk.Label(box2, text="Deje vacío lo que no cambia").grid(row=6, column=0, columnspan=2)
        btns = ttk.Frame(box2)
        btns.grid(row=7, column=0, columnspan=2, pady=3)
        ttk.Button(btns, text="Corregir…", command=self.do_correct).pack(side="left", padx=2)
        ttk.Button(btns, text="Eliminar…", command=self.do_delete).pack(side="left", padx=2)
        ttk.Button(btns, text="Revisado", command=self.do_review).pack(side="left", padx=2)
        frame, self.ev_info = text_box(right, height=8, width=44)
        frame.pack(fill="x", pady=3)

        def refresh():
            fill(self.ev_table, self.ctl.event_rows())
            if self.selected is not None:
                set_text(self.ev_info, self.ctl.describe(self.selected).message)
        return refresh

    def _pick_event_row(self, _event):
        picked = self.ev_table.selection()
        if picked:
            text = self.ev_table.item(picked[0], "values")[0]
            self.fix_id.set(text)
            try:
                self.selected = int(str(text).replace("SIS-", ""))
            except ValueError:
                return
            set_text(self.ev_info, self.ctl.describe(self.selected).message)

    def do_create(self):
        v = {k: var.get().strip() for k, var in self.new_vars.items()}
        if self.act(self.ctl.create(v["id"], v["magnitude"], v["depth"], v["x"], v["y"], v["time"],
                                    v["station"])):
            self.selected = int(v["id"].upper().replace("SIS-", ""))

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
        right = ttk.LabelFrame(top, text="Preparar ráfaga")
        right.pack(side="right", fill="y", padx=6)
        defaults = {"revision": "1", "time": format_time(self.ctl.catalog.clock)}
        self.burst_vars = form(right, BURST_FIELDS, defaults=defaults, width=20)
        row = len(BURST_FIELDS)
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
        self.running = True
        self.say(self._ok("Procesamiento continuo iniciado (un reporte por tick)."))
        self._tick()

    def stop_continuous(self):
        self.running = False
        self.say(self._ok("Procesamiento continuo en pausa."))

    def _tick(self):
        if not self.running:
            return
        if not self.do_step(continuous=True):
            self.running = False              # empty queue or recovery pause: stop, the log says why
            return
        try:
            delay = max(50, int(self.delay.get()))
        except ValueError:
            delay = 700
        self.root.after(delay, self._tick)

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
                ttk.Label(sub, text=label).pack(side="left")
                ttk.Entry(sub, textvariable=self.q[var], width=22 if var in ("start", "end") else 8
                          ).pack(side="left")
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
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

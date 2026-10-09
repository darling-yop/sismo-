"""Smoke test of ui.app WITHOUT a display: tkinter is replaced by a fake module.

It checks that every screen builds and refreshes, and that every button
handler runs against the real controller. It cannot check pixels; run
`python main.py` for that.
"""

import importlib
import os
import sys
import tempfile
import types
import unittest

from services.persistence import write_json

T = "2026-09-07T10:00:00Z"


class Widget:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.after_calls = []

    def __getattr__(self, name):
        return lambda *a, **k: None

    def get_children(self):
        return ()

    def selection(self):
        return ()

    def item(self, *a, **k):
        return ("",)

    def canvasx(self, x):
        return x

    canvasy = canvasx

    def after(self, delay, fn):
        self.after_calls.append(fn)


class Notebook(Widget):
    current = 0

    def select(self, index=None):
        if index is not None:
            self.current = index
        return self.current

    def index(self, value):
        return value


class Var:
    def __init__(self, master=None, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def fake_modules(dialogs):
    tk = types.ModuleType("tkinter")
    ttk = types.ModuleType("tkinter.ttk")
    fd = types.ModuleType("tkinter.filedialog")
    mb = types.ModuleType("tkinter.messagebox")
    for name in ("Tk", "Canvas", "Text", "Frame"):
        setattr(tk, name, Widget)
    tk.StringVar = Var
    for name in ("Frame", "Label", "Button", "Entry", "Combobox", "Spinbox", "Scrollbar", "Treeview",
                 "LabelFrame", "Panedwindow", "Separator"):
        setattr(ttk, name, Widget)
    tk.Label = Widget
    ttk.Notebook = Notebook
    fd.askopenfilename = lambda **k: dialogs["open"]
    fd.asksaveasfilename = lambda **k: dialogs["save"]
    fd.askdirectory = lambda **k: dialogs["dir"]
    mb.askyesno = lambda *a, **k: True
    mb.showerror = lambda *a, **k: dialogs.setdefault("errors", []).append(a)
    mb.showinfo = lambda *a, **k: None
    tk.ttk, tk.filedialog, tk.messagebox = ttk, fd, mb
    return {"tkinter": tk, "tkinter.ttk": ttk, "tkinter.filedialog": fd, "tkinter.messagebox": mb}


class AppSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dialogs = {"open": "", "save": "", "dir": self.tmp.name}
        self.saved = {k: sys.modules.get(k) for k in ("tkinter", "tkinter.ttk", "tkinter.filedialog",
                                                      "tkinter.messagebox", "ui.app")}
        sys.modules.update(fake_modules(self.dialogs))
        sys.modules.pop("ui.app", None)
        self.module = importlib.import_module("ui.app")
        self.app = self.module.App(Widget())
        self.addCleanup(self.restore)

    def restore(self):
        for key, value in self.saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def test_every_tab_refreshes(self):
        app = self.app
        for index in range(len(app.tab_names)):
            app.nb.select(index)
            app.refresh()

    def test_full_workflow(self):
        app = self.app
        for key, value in dict(id="1", magnitude="6.5", depth="10.0", x="100.0", y="100.0",
                               time=T, station="A").items():
            app.new_vars[key].set(value)
        app.do_create()
        self.assertEqual(list(app.ctl.catalog.active), [1])
        self.assertEqual(app.selected, 1)
        app.new_vars["id"].set("2")
        app.new_vars["magnitude"].set("1.0")
        app.do_create()
        app.fix_id.set("1")
        app.fix_vars["magnitude"].set("4.0")
        app.do_correct()
        self.assertEqual(app.ctl.catalog.active[1].magnitude, 4.0)
        app.do_review()
        app.review_selected()
        app.delete_selected()
        app.do_delete()
        app.fix_id.set("2")
        app.do_delete()
        self.assertEqual(len(app.ctl.catalog.active), 0)
        app.act(app.ctl.undo())
        app.toggle_stress()
        self.assertTrue(app.ctl.catalog.avl.stress)
        app.toggle_stress()
        app.params["W"].set("60")
        app.apply_params()
        self.assertEqual(app.ctl.catalog.W, 60.0)

    def test_queue_and_continuous(self):
        app = self.app
        for i in range(3):
            for key, value in dict(station="A", event_id=str(i + 1), revision="1", magnitude="1.0",
                                   depth="10.0", x="1.0", y="1.0", time=T).items():
                app.burst_vars[key].set(value)
            app.add_draft()
        app.send_draft()
        self.assertEqual(len(app.ctl.queue), 3)
        app.do_step()
        app.start_continuous()
        for _ in range(10):                           # run the scheduled ticks
            pending, app.root.after_calls = app.root.after_calls, []
            for fn in pending:
                fn()
        self.assertEqual(len(app.ctl.queue), 0)
        self.assertFalse(app.running)
        app.stop_continuous()
        app.send_draft()                              # empty draft: message only

    def test_files_versions_archive_audit_queries(self):
        app = self.app
        events = [{"id": i, "magnitude": i / 10, "depth": 10.0, "x": 1.0, "y": 1.0, "time": T,
                   "station": "A"} for i in range(1, 21)]
        write_json(self.path("ins.json"), {"kind": "sismolab-insertions", "events": events})
        self.dialogs["open"] = self.path("ins.json")
        app.load_insertions()
        self.assertEqual(len(app.ctl.catalog.active), 20)
        self.dialogs["save"] = self.path("state.json")
        app.save_state()
        self.dialogs["open"] = self.path("state.json")
        app.load_topology()
        write_json(self.path("bad.json"), {"kind": "otra-cosa"})
        self.dialogs["open"] = self.path("bad.json")
        app.load_topology()
        self.assertTrue(self.dialogs.get("errors"))
        write_json(self.path("burst.json"), {"kind": "sismolab-reports", "reports": [
            dict(station="A", event_id=1, revision=1, magnitude=0.1, depth=10.0, x=1.0, y=1.0, time=T)]})
        self.dialogs["open"] = self.path("burst.json")
        app.load_burst()
        self.assertEqual(len(app.ctl.queue), 1)
        app.pick_folder()
        app.ver_name.set("v1")
        app.save_version()
        app.restore_version()
        app.ctl.advance_clock(500)
        app.preview_archive()
        app.do_archive()
        app.run_audit()
        for name in ("top", "magnitude", "dates", "associations", "costly"):
            app.q["id"].set("3")
            app.run_query(name)
        app.q["k"].set("0")
        app.run_query("top")


if __name__ == "__main__":
    unittest.main()

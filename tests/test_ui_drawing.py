import unittest

from domain.models import Zone
from services.scenario import Scenario
from ui.controller import Controller
from ui.drawing import (COSTLY_COLOR, PRIORITY_COLORS, draw_legend, draw_plane, draw_tree,
                        hit_node, hit_point)

T = "2026-09-07T10:00:00Z"


class FakeCanvas:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return 1
        return call

    def of(self, name):
        return [c for c in self.calls if c[0] == name]


def build():
    c = Controller(Scenario(zones=[Zone("Z", 0.0, 0.0, 500.0, 500.0, True)]))
    c.set_parameters("", "", "0", "")                      # L=0 -> deep high events are costly
    for i, m in enumerate(["6.1", "6.2", "6.3", "6.4", "1.0", "2.0"], start=1):
        c.create(i, m, "10.0", "100.0", "100.0", T, "A")
    return c


class TreeDrawingTest(unittest.TestCase):
    def test_nodes_colors_costly_and_hits(self):
        c = build()
        view = c.tree_view()
        canvas = FakeCanvas()
        hits = draw_tree(canvas, view["layout"], view["events"], view["costly"], view["imbalanced"])
        self.assertEqual(len(hits), 6)
        self.assertEqual(len(canvas.of("create_rectangle")), 6)
        fills = {k["fill"] for _, _, k in canvas.of("create_rectangle")}
        self.assertTrue(fills <= set(PRIORITY_COLORS.values()))
        self.assertTrue(view["costly"])
        purple = [k for _, _, k in canvas.of("create_rectangle") if k.get("outline") == COSTLY_COLOR]
        self.assertEqual(len(purple), len(view["costly"]))
        eid, x1, y1, x2, y2 = hits[0]
        self.assertEqual(hit_node(hits, (x1 + x2) / 2, (y1 + y2) / 2), eid)
        self.assertIsNone(hit_node(hits, -5, -5))

    def test_empty_and_legend(self):
        canvas = FakeCanvas()
        c = Controller()
        view = c.tree_view()
        self.assertEqual(draw_tree(canvas, view["layout"], {}), [])
        draw_legend(canvas)
        self.assertTrue(canvas.of("create_text"))

    def test_stress_marks_imbalance(self):
        c = Controller()
        c.set_stress(True)
        for i in range(1, 8):
            c.create(i, str(i / 10), "10.0", "900.0", "900.0", T, "A")
        view = c.tree_view()
        canvas = FakeCanvas()
        draw_tree(canvas, view["layout"], view["events"], view["costly"], view["imbalanced"])
        self.assertTrue(any("¡" in k.get("text", "") for _, _, k in canvas.of("create_text")))


class PlaneDrawingTest(unittest.TestCase):
    def test_plane(self):
        c = build()
        c.advance_clock(500)
        c.archive()
        view = c.plane_view()
        canvas = FakeCanvas()
        hits = draw_plane(canvas, view)
        self.assertEqual(len(hits), 6)
        self.assertEqual(len(canvas.of("create_oval")), 6)
        _, cx, cy, _ = hits[0]
        self.assertEqual(hit_point(hits, cx, cy), hits[0][0])
        self.assertIsNone(hit_point(hits, -100, -100))


if __name__ == "__main__":
    unittest.main()

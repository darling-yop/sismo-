"""Mouse navigation helpers for the AVL canvas."""


class TreeCanvasNavigator:
    def __init__(self, canvas):
        self.canvas = canvas
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.dragged = False
        self._press = None
        canvas.bind("<MouseWheel>", self._wheel)
        canvas.bind("<Button-4>", lambda event: self._zoom(event, 1.12))
        canvas.bind("<Button-5>", lambda event: self._zoom(event, 0.89))
        canvas.bind("<ButtonPress-1>", self._press_mouse)
        canvas.bind("<B1-Motion>", self._drag)
        canvas.bind("<ButtonRelease-1>", self._release_mouse)

    def _press_mouse(self, event):
        self._press = (event.x, event.y)
        self.dragged = False
        self.canvas.scan_mark(event.x, event.y)

    def _drag(self, event):
        if self._press and (abs(event.x - self._press[0]) > 3 or
                            abs(event.y - self._press[1]) > 3):
            self.dragged = True
            self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _release_mouse(self, _event):
        self._press = None

    def _wheel(self, event):
        self._zoom(event, 1.12 if event.delta > 0 else 0.89)

    def _zoom(self, event, factor):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self._zoom_at(x, y, factor)

    def zoom_center(self, factor):
        x = self.canvas.winfo_width() / 2
        y = self.canvas.winfo_height() / 2
        self._zoom_at(x, y, factor)

    def _zoom_at(self, x, y, factor):
        self.canvas.scale("all", x, y, factor, factor)
        self.scale *= factor
        self.offset_x = x + (self.offset_x - x) * factor
        self.offset_y = y + (self.offset_y - y) * factor
        self._update_scrollregion()

    def reset_for_redraw(self):
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def apply_after_redraw(self):
        if self.scale != 1.0:
            self.canvas.scale("all", 0, 0, self.scale, self.scale)
        if self.offset_x or self.offset_y:
            self.canvas.move("all", self.offset_x, self.offset_y)
        self._update_scrollregion()

    def fit(self):
        self.canvas.update_idletasks()
        bounds = self.canvas.bbox("all")
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if not bounds or width <= 1 or height <= 1:
            return
        content_width = max(bounds[2] - bounds[0], 1)
        content_height = max(bounds[3] - bounds[1], 1)
        factor = min((width - 28) / content_width, (height - 28) / content_height, 1.0)
        self.canvas.scale("all", 0, 0, factor, factor)
        bounds = self.canvas.bbox("all")
        dx = (width - (bounds[2] - bounds[0])) / 2 - bounds[0]
        dy = (height - (bounds[3] - bounds[1])) / 2 - bounds[1]
        self.canvas.move("all", dx, dy)
        self.scale = factor
        self.offset_x = dx
        self.offset_y = dy
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

    def to_world(self, x, y):
        if self.scale == 0:
            return x, y
        return (x - self.offset_x) / self.scale, (y - self.offset_y) / self.scale

    def _update_scrollregion(self):
        bounds = self.canvas.bbox("all")
        if bounds:
            self.canvas.configure(scrollregion=bounds)

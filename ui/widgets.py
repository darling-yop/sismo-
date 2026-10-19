"""Small reusable Tk widgets shared by the SismoLab screens."""

import tkinter as tk
import calendar
from datetime import date, datetime
from tkinter import ttk

from ui import theme


def collapsible_card(parent, title, expanded=False):
    card = ttk.Frame(parent, style="Card.TFrame", padding=8)
    icon, label = title[:1], title[1:].strip()
    header = ttk.Button(card, text=f"{'▾' if expanded else '▸'}  {icon}  {label}",
                        style="Card.TButton")
    header.pack(fill="x")
    body = ttk.Frame(card, style="Card.TFrame", padding=(4, 7, 4, 2))
    state = {"expanded": expanded}

    def toggle():
        state["expanded"] = not state["expanded"]
        if state["expanded"]:
            header.configure(text=f"▾  {icon}  {label}")
            body.pack(fill="x")
        else:
            header.configure(text=f"▸  {icon}  {label}")
            body.pack_forget()

    header.configure(command=toggle)
    if expanded:
        body.pack(fill="x")
    return card, body


def metric_card(parent, name, value="—", accent=None):
    card = ttk.Frame(parent, style="Metric.TFrame", padding=(7, 5))
    title = ttk.Label(card, text=name.upper(), style="MetricName.TLabel")
    title.pack(anchor="w")
    value_label = ttk.Label(card, text=str(value), style="MetricValue.TLabel")
    value_label.pack(anchor="w")
    if accent:
        value_label.configure(foreground=accent)
    return card, value_label


def linked_form(parent, fields, variables, width=16, on_enter=None, row=0):
    entries = {}
    for offset, (name, label) in enumerate(fields):
        field_row = row + offset * 2
        ttk.Label(parent, text=label, style="Card.TLabel").grid(
            row=field_row, column=0, sticky="w", padx=3, pady=(4, 1))
        entry = ttk.Entry(parent, textvariable=variables[name], width=width)
        entry.grid(row=field_row + 1, column=0, columnspan=2, sticky="ew",
                   padx=3, pady=(0, 3))
        if on_enter:
            entry.bind("<Return>", lambda _event, callback=on_enter: callback())
        entries[name] = entry
    parent.columnconfigure(0, weight=1)
    return entries


def set_placeholder(entry, variable, text, on_touch=None):
    variable.set(text)
    entry.configure(style="Placeholder.TEntry")

    def focus_in(_event):
        if variable.get() == text:
            variable.set("")
        entry.configure(style="TEntry")

    def focus_out(_event):
        if not variable.get().strip():
            variable.set(text)
            entry.configure(style="Placeholder.TEntry")
        if on_touch:
            on_touch()

    entry.bind("<FocusIn>", focus_in, add="+")
    entry.bind("<FocusOut>", focus_out, add="+")
    entry.bind("<KeyRelease>", lambda _event: on_touch() if on_touch else None, add="+")


def utc_picker(parent, variable, initial, on_change=None):
    try:
        moment = datetime.strptime(initial, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        moment = datetime.utcnow()
    frame = ttk.Frame(parent, style="Card.TFrame")
    date_var = tk.StringVar(value=moment.strftime("%Y-%m-%d"))
    time_var = tk.StringVar(value=moment.strftime("%H:%M"))
    ttk.Label(frame, text="Fecha UTC · AAAA-MM-DD", style="Card.TLabel").grid(
        row=0, column=0, sticky="w", padx=3, pady=(4, 1))
    date_row = ttk.Frame(frame, style="Card.TFrame")
    date_row.grid(row=1, column=0, sticky="ew", padx=3, pady=(0, 5))
    date_entry = ttk.Entry(date_row, textvariable=date_var)
    date_entry.pack(side="left", fill="x", expand=True)
    calendar_button = ttk.Button(date_row, text="▦", width=3)
    calendar_button.pack(side="right", padx=(4, 0))
    ttk.Label(frame, text="Hora UTC · HH:MM", style="Card.TLabel").grid(
        row=2, column=0, sticky="w", padx=3, pady=(4, 1))
    time_entry = ttk.Entry(frame, textvariable=time_var)
    time_entry.grid(row=3, column=0, sticky="ew", padx=3, pady=(0, 4))
    frame.columnconfigure(0, weight=1)
    error = ttk.Label(frame, text="", style="Validation.TLabel")
    error.grid(row=4, column=0, sticky="w", padx=3)
    valid = {"value": True}

    def apply_value():
        try:
            parsed = datetime.strptime(f"{date_var.get().strip()} {time_var.get().strip()}",
                                       "%Y-%m-%d %H:%M")
        except ValueError:
            valid["value"] = False
            error.configure(text="Use AAAA-MM-DD y HH:MM válidos.")
            date_entry.configure(style="Invalid.TEntry")
            time_entry.configure(style="Invalid.TEntry")
            if on_change:
                on_change()
            return False
        variable.set(parsed.strftime("%Y-%m-%dT%H:%M:%SZ"))
        valid["value"] = True
        error.configure(text="")
        date_entry.configure(style="TEntry")
        time_entry.configure(style="TEntry")
        if on_change:
            on_change()
        return True

    def open_calendar():
        try:
            current = datetime.strptime(date_var.get(), "%Y-%m-%d").date()
        except ValueError:
            current = moment.date()
        popup = tk.Toplevel(frame)
        popup.title("Seleccionar fecha UTC")
        popup.configure(bg=theme.PALETTE["surface"])
        popup.transient(frame.winfo_toplevel())
        state = {"year": current.year, "month": current.month}
        months = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio",
                  "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
        heading = ttk.Frame(popup, style="Card.TFrame", padding=6)
        heading.pack(fill="x")
        title = ttk.Label(heading, style="Card.TLabel")
        title.pack(side="left", expand=True)
        grid = ttk.Frame(popup, style="Card.TFrame", padding=6)
        grid.pack()

        def render():
            for child in grid.winfo_children():
                child.destroy()
            title.configure(text=f"{months[state['month']].capitalize()} {state['year']}")
            for column, name in enumerate(("L", "M", "X", "J", "V", "S", "D")):
                ttk.Label(grid, text=name, style="Muted.TLabel").grid(row=0, column=column, padx=4)
            for row, week in enumerate(calendar.monthcalendar(state["year"], state["month"]), start=1):
                for column, day_number in enumerate(week):
                    if day_number:
                        ttk.Button(
                            grid, text=str(day_number), width=3,
                            command=lambda selected=day_number: choose(selected)
                        ).grid(row=row, column=column, padx=1, pady=1)

        def previous():
            state["year"], state["month"] = (
                (state["year"] - 1, 12) if state["month"] == 1
                else (state["year"], state["month"] - 1))
            render()

        def next_month():
            state["year"], state["month"] = (
                (state["year"] + 1, 1) if state["month"] == 12
                else (state["year"], state["month"] + 1))
            render()

        def choose(day_number):
            date_var.set(date(state["year"], state["month"], day_number).isoformat())
            date_entry.configure(style="TEntry")
            apply_value()
            popup.destroy()

        ttk.Button(heading, text="‹", width=3, command=previous).pack(side="left")
        ttk.Button(heading, text="›", width=3, command=next_month).pack(side="right")
        render()

    calendar_button.configure(command=open_calendar)
    for entry in (date_entry, time_entry):
        entry.bind("<KeyRelease>", lambda _event: apply_value())
        entry.bind("<FocusOut>", lambda _event: apply_value())
    date_entry.configure(style="TEntry")
    time_entry.configure(style="TEntry")
    return frame, apply_value, valid, date_entry, time_entry


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.window = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None):
        if self.window is not None:
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.window.wm_geometry(f"+{x}+{y}")
        ttk.Label(self.window, text=self.text, padding=6).pack()

    def _hide(self, _event=None):
        if self.window is not None:
            self.window.destroy()
            self.window = None


def card_label(parent, text, style="Card.TLabel"):
    return ttk.Label(parent, text=text, style=style)

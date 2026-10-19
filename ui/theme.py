"""SismoLab visual tokens and reusable ttk styles."""

from tkinter import ttk

PALETTE = {
    "background": "#0B1220",
    "surface": "#121A2B",
    "surface_alt": "#182337",
    "border": "#1E2A44",
    "text": "#E6EDF7",
    "muted": "#91A0B8",
    "disabled_text": "#6B7A99",
    "cyan": "#22D3EE",
    "cyan_hover": "#67E8F9",
    "high": "#FF6B6B",
    "medium": "#FBBF24",
    "low": "#34D399",
    "violet": "#A78BFA",
    "warning": "#FDE047",
    "white": "#FFFFFF",
    "black": "#07101D",
    "ok": "#34D399",
    "error": "#FF6B6B",
    "grid": "#26334C",
    "zone_populated": "#243D4C",
    "zone_empty": "#202B3D",
    "archived": "#91A0B8",
}

FONTS = {
    "ui": ("Segoe UI", 10),
    "ui_small": ("Segoe UI", 10),
    "ui_bold": ("Segoe UI", 10, "bold"),
    "heading": ("Segoe UI", 14, "bold"),
    "brand": ("Segoe UI", 14, "bold"),
    "metric": ("Segoe UI", 18, "bold"),
    "mono": ("Segoe UI", 10),
    "mono_small": ("Segoe UI", 10),
}

PRIORITY_COLORS = {3: PALETTE["high"], 2: PALETTE["medium"], 1: PALETTE["low"]}
PRIORITY_NAMES = {3: "alta", 2: "media", 1: "baja"}


def configure_styles(root):
    """Apply the dark palette when the active Tk implementation exposes ttk styles."""
    tk_interpreter = getattr(root, "tk", None)
    if not callable(getattr(tk_interpreter, "call", None)):
        return
    style_factory = getattr(ttk, "Style", None)
    if style_factory is None:
        return
    style = style_factory(root)
    style.theme_use("clam")
    style.configure(".", background=PALETTE["background"], foreground=PALETTE["text"],
                    font=FONTS["ui"])
    style.configure("TFrame", background=PALETTE["background"])
    style.configure("Surface.TFrame", background=PALETTE["surface"])
    style.configure("Card.TFrame", background=PALETTE["surface"], relief="solid",
                    borderwidth=1, bordercolor=PALETTE["border"])
    style.configure("TLabel", background=PALETTE["background"], foreground=PALETTE["text"])
    style.configure("Muted.TLabel", background=PALETTE["surface"], foreground=PALETTE["muted"])
    style.configure("Card.TLabel", background=PALETTE["surface"], foreground=PALETTE["text"])
    style.configure("Brand.TLabel", background=PALETTE["background"], foreground=PALETTE["cyan"],
                    font=FONTS["brand"])
    style.configure("Metric.TFrame", background=PALETTE["surface"], borderwidth=1,
                    relief="solid")
    style.configure("MetricName.TLabel", background=PALETTE["surface"], foreground=PALETTE["muted"],
                    font=FONTS["ui_small"])
    style.configure("MetricValue.TLabel", background=PALETTE["surface"], foreground=PALETTE["cyan"],
                    font=FONTS["metric"])
    style.configure("TButton", background=PALETTE["surface_alt"], foreground=PALETTE["text"],
                    bordercolor=PALETTE["border"], borderwidth=1, relief="flat", padding=(9, 5))
    style.map("TButton", background=[("active", PALETTE["border"]),
                                     ("disabled", PALETTE["border"])],
              foreground=[("disabled", PALETTE["disabled_text"])])
    style.configure("Primary.TButton", background=PALETTE["cyan"], foreground=PALETTE["background"],
                    bordercolor=PALETTE["cyan"], borderwidth=1, relief="flat",
                    font=FONTS["ui_bold"])
    style.map("Primary.TButton", background=[("active", PALETTE["cyan_hover"])])
    style.map("Primary.TButton", background=[("disabled", PALETTE["border"]),
                                             ("active", PALETTE["cyan_hover"])],
              foreground=[("disabled", PALETTE["disabled_text"])])
    style.configure("Card.TButton", background=PALETTE["surface"], foreground=PALETTE["cyan"],
                    anchor="w", padding=(7, 5), bordercolor=PALETTE["border"],
                    borderwidth=1, relief="flat")
    style.map("Card.TButton", background=[("active", PALETTE["surface_alt"])])
    style.configure("TEntry", fieldbackground=PALETTE["surface"], foreground=PALETTE["text"],
                    insertcolor=PALETTE["text"], bordercolor=PALETTE["border"],
                    lightcolor=PALETTE["border"], darkcolor=PALETTE["border"],
                    borderwidth=1, relief="flat", padding=7, font=FONTS["ui"])
    style.configure("Invalid.TEntry", fieldbackground=PALETTE["surface_alt"],
                    foreground=PALETTE["text"], insertcolor=PALETTE["text"],
                    bordercolor=PALETTE["error"], lightcolor=PALETTE["error"],
                    darkcolor=PALETTE["error"], borderwidth=1, relief="flat",
                    padding=7, font=FONTS["ui"])
    style.configure("Placeholder.TEntry", fieldbackground=PALETTE["surface"],
                    foreground=PALETTE["muted"], insertcolor=PALETTE["text"],
                    bordercolor=PALETTE["border"], lightcolor=PALETTE["border"],
                    darkcolor=PALETTE["border"], borderwidth=1, relief="flat",
                    padding=7, font=FONTS["ui"])
    style.configure("Validation.TLabel", background=PALETTE["surface"],
                    foreground=PALETTE["error"], font=FONTS["ui_small"])
    style.configure("TCombobox", fieldbackground=PALETTE["surface_alt"],
                    background=PALETTE["surface_alt"], foreground=PALETTE["text"])
    style.configure("TSpinbox", fieldbackground=PALETTE["surface_alt"], foreground=PALETTE["text"])
    style.configure("TLabelframe", background=PALETTE["surface"], foreground=PALETTE["muted"],
                    bordercolor=PALETTE["border"])
    style.configure("TLabelframe.Label", background=PALETTE["surface"], foreground=PALETTE["cyan"],
                    font=FONTS["ui_bold"])
    style.configure("TNotebook", background=PALETTE["background"], borderwidth=0)
    style.configure("TNotebook.Tab", background=PALETTE["surface"], foreground=PALETTE["muted"],
                    padding=(9, 7), borderwidth=0, width=0, font=FONTS["ui"])
    style.map("TNotebook.Tab", background=[("selected", PALETTE["cyan"])],
              foreground=[("selected", PALETTE["black"])])
    style.configure("Treeview", background=PALETTE["surface"], fieldbackground=PALETTE["surface"],
                    foreground=PALETTE["text"], bordercolor=PALETTE["border"], rowheight=28,
                    font=FONTS["ui"], relief="flat", borderwidth=1)
    style.configure("Treeview.Heading", background=PALETTE["surface_alt"],
                    foreground=PALETTE["cyan"], font=FONTS["ui_bold"])
    style.map("Treeview", background=[("selected", PALETTE["border"])],
              foreground=[("selected", PALETTE["text"])])
    style.configure("ModeNormal.TLabel", background=PALETTE["low"], foreground=PALETTE["black"],
                    font=FONTS["ui_bold"], padding=(10, 5))
    style.configure("ModeStress.TLabel", background=PALETTE["high"], foreground=PALETTE["black"],
                    font=FONTS["ui_bold"], padding=(10, 5))
    style.configure("Banner.TLabel", background=PALETTE["high"], foreground=PALETTE["black"],
                    font=FONTS["ui_bold"], padding=7)
    style.configure("Horizontal.TSeparator", background=PALETTE["border"])
    style.configure("Vertical.TSeparator", background=PALETTE["border"])

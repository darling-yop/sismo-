"""Application window factory."""

import tkinter as tk


def launch(root=None, controller=None):
    from ui.app import App

    window = root or tk.Tk()
    App(window, controller=controller)
    if root is None:
        window.mainloop()
    return window

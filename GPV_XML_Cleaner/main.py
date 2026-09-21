"""
Entry point for GPV XML Cleaner & Diagnostics.

Run with:
    python main.py
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app import config
from app.gui import App


def main() -> None:
    config.ensure_directories()
    logger = config.get_logger()
    logger.info("Application starting: %s", config.APP_NAME)

    root = tk.Tk()

    def handle_exception(exc_type, exc_value, exc_tb) -> None:
        logger.error("Unhandled GUI exception", exc_info=(exc_type, exc_value, exc_tb))
        try:
            messagebox.showerror("Error inesperado", f"Ocurrió un error inesperado:\n{exc_value}")
        except Exception:
            pass

    root.report_callback_exception = handle_exception

    App(root)
    root.mainloop()
    logger.info("Application closed")


if __name__ == "__main__":
    main()

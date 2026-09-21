"""
Tkinter GUI for GPV XML Cleaner & Diagnostics.

Single App class driving a modern, operator-friendly dashboard: folder
scanning runs in a background thread (UI stays responsive), while every
destructive action (moving/deleting files) requires an explicit,
multi-step confirmation and defaults to SAFE MODE (move, never delete).
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

import uvicorn

from app import cleanup, config, scanner
from app import statistics as stats_module
from app.api import api_app
from app.api import state as api_state
from app.models import ScanResult, XMLFileInfo, format_size

logger = config.get_logger()

COLORS = {
    "bg_header": "#1b2431",
    "bg_app": "#eef1f5",
    "card_bg": "#ffffff",
    "text_dark": "#1b2431",
    "text_muted": "#6b7280",
    "accent": "#2c7be5",
    "accent_dark": "#1f5fb8",
    "green": "#27ae60",
    "yellow": "#f1c40f",
    "orange": "#e67e22",
    "red": "#e74c3c",
    "border": "#d8dde3",
}

STATUS_TAGS = {
    "RECENT": "status_recent",
    "REVIEW": "status_review",
    "OLD": "status_old",
    "VERY OLD": "status_very_old",
}

FILTER_OPTIONS = [
    "Todos",
    "Hoy",
    "Últimas 24 horas",
    "Últimos 7 días",
    "Últimos 30 días",
    "Más de 30 días",
    "Más de 60 días",
    "Más de 90 días",
]

RETENTION_OPTIONS = ["1 día", "3 días", "7 días", "15 días", "30 días", "60 días", "90 días", "Personalizado"]
RETENTION_DAYS_MAP = {"1 día": 1, "3 días": 3, "7 días": 7, "15 días": 15, "30 días": 30, "60 días": 60, "90 días": 90}
REV_RETENTION_MAP = {v: k for k, v in RETENTION_DAYS_MAP.items()}

TREE_COLUMNS = ("name", "created", "modified", "age", "size", "path", "status", "recommendation")
TREE_HEADINGS = {
    "name": "Nombre",
    "created": "Fecha creación",
    "modified": "Última modificación",
    "age": "Antigüedad",
    "size": "Tamaño",
    "path": "Ruta",
    "status": "Estado",
    "recommendation": "Recomendación",
}
TREE_WIDTHS = {
    "name": 220,
    "created": 150,
    "modified": 150,
    "age": 90,
    "size": 80,
    "path": 320,
    "status": 90,
    "recommendation": 140,
}
SORT_KEYS = {
    "name": lambda f: f.name.lower(),
    "created": lambda f: f.created,
    "modified": lambda f: f.modified,
    "age": lambda f: f.age_days,
    "size": lambda f: f.size_bytes,
    "path": lambda f: f.path.lower(),
    "status": lambda f: f.status,
    "recommendation": lambda f: f.recommendation,
}


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings = config.load_settings()

        self.current_folder: str = ""
        self.scan_result: Optional[ScanResult] = None
        self.all_files: List[XMLFileInfo] = []
        self.filtered_files: List[XMLFileInfo] = []
        self.sort_column = "modified"
        self.sort_reverse = False
        self.scanning = False
        self.cancel_event: Optional[threading.Event] = None
        self.cleanup_cancel_event: Optional[threading.Event] = None
        self.scan_queue: "queue.Queue" = queue.Queue()
        self.move_queue: "queue.Queue" = queue.Queue()
        self._search_after_id: Optional[str] = None
        self._tree_generation = 0
        self._search_placeholder = "Buscar XML..."
        self.api_server: Optional[uvicorn.Server] = None

        self.root.title(config.APP_NAME)
        self.root.geometry("1200x750")
        self.root.minsize(1024, 640)

        self._build_style()
        self._build_header()
        self._build_footer()
        self._build_toolbar()
        self._build_progress_area()
        self._build_cards()
        self._build_oldest_panel()
        self._build_notebook()

        last_folder = self.settings.get("last_folder", "")
        if last_folder and os.path.isdir(last_folder):
            self.current_folder = last_folder
            self.folder_path_var.set(last_folder)
            self.btn_rescan.config(state="normal")

        self._start_api()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------
    def _build_style(self) -> None:
        self.root.configure(bg=COLORS["bg_app"])
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COLORS["bg_app"])
        style.configure("TNotebook", background=COLORS["bg_app"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 9, "bold"))
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["card_bg"])],
            foreground=[("selected", COLORS["accent"])],
        )
        style.configure(
            "Treeview",
            rowheight=24,
            font=("Segoe UI", 9),
            background=COLORS["card_bg"],
            fieldbackground=COLORS["card_bg"],
        )
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#e7ebef")
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground="white",
            font=("Segoe UI", 10, "bold"),
            padding=(14, 8),
        )
        style.map("Accent.TButton", background=[("active", COLORS["accent_dark"])])
        style.configure(
            "Secondary.TButton",
            background="#e7ebef",
            foreground=COLORS["text_dark"],
            font=("Segoe UI", 9),
            padding=(10, 6),
        )
        style.map("Secondary.TButton", background=[("active", "#d8dde3")])
        style.configure(
            "Danger.TButton",
            background=COLORS["red"],
            foreground="white",
            font=("Segoe UI", 10, "bold"),
            padding=(14, 8),
        )
        style.map("Danger.TButton", background=[("active", "#c0392b")])
        style.configure("TCheckbutton", background=COLORS["bg_app"], font=("Segoe UI", 9))
        style.configure("Card.TCheckbutton", background=COLORS["card_bg"], font=("Segoe UI", 9))
        style.configure("TCombobox", padding=4)
        style.configure("TEntry", padding=4)

    # ------------------------------------------------------------------
    # Header / footer / toolbar
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=COLORS["bg_header"], height=90)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        left = tk.Frame(header, bg=COLORS["bg_header"])
        left.pack(side="left", padx=24, pady=14, anchor="w")
        tk.Label(
            left,
            text="GPV XML Cleaner & Diagnostics",
            font=("Segoe UI", 20, "bold"),
            bg=COLORS["bg_header"],
            fg="white",
        ).pack(anchor="w")
        tk.Label(
            left,
            text="Selecciona tu carpeta FLX y te digo todo",
            font=("Segoe UI", 10),
            bg=COLORS["bg_header"],
            fg="#9aa5b1",
        ).pack(anchor="w")

        right = tk.Frame(header, bg=COLORS["bg_header"])
        right.pack(side="right", padx=24)
        status_frame = tk.Frame(right, bg=COLORS["bg_header"])
        status_frame.pack(anchor="e", pady=34)
        self.status_dot = tk.Label(
            status_frame, text="●", font=("Segoe UI", 14), bg=COLORS["bg_header"], fg=COLORS["green"]
        )
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(
            status_frame,
            text="SYSTEM READY",
            font=("Segoe UI", 10, "bold"),
            bg=COLORS["bg_header"],
            fg="white",
        )
        self.status_text.pack(side="left", padx=(6, 0))

    def _build_footer(self) -> None:
        footer = tk.Frame(self.root, bg=COLORS["bg_header"], height=26)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Label(
            footer,
            text=f"Logs: {config.LOG_FILE}",
            bg=COLORS["bg_header"],
            fg="#9aa5b1",
            font=("Segoe UI", 8),
        ).pack(side="left", padx=12)
        self.api_status_var = tk.StringVar(
            value=f"API: http://{self.settings.get('api_host', '127.0.0.1')}:{self.settings.get('api_port', 8765)}"
        )
        tk.Label(
            footer, textvariable=self.api_status_var, bg=COLORS["bg_header"], fg="#9aa5b1", font=("Segoe UI", 8)
        ).pack(side="right", padx=12)

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=COLORS["bg_app"])
        bar.pack(fill="x", padx=20, pady=(14, 6))

        self.btn_select = ttk.Button(
            bar, text="📁 Seleccionar carpeta FLX", style="Accent.TButton", command=self.select_folder
        )
        self.btn_select.pack(side="left")

        self.btn_rescan = ttk.Button(
            bar, text="🔄 Volver a revisar", style="Secondary.TButton", command=self.start_scan, state="disabled"
        )
        self.btn_rescan.pack(side="left", padx=(10, 0))

        ttk.Button(bar, text="⚙ Configuración", style="Secondary.TButton", command=self.open_settings_dialog).pack(
            side="right"
        )
        ttk.Button(bar, text="📤 Exportar reporte", style="Secondary.TButton", command=self.export_report).pack(
            side="right", padx=(0, 8)
        )

        path_bar = tk.Frame(self.root, bg=COLORS["bg_app"])
        path_bar.pack(fill="x", padx=20)
        tk.Label(
            path_bar, text="Carpeta:", bg=COLORS["bg_app"], fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")
        ).pack(side="left")
        self.folder_path_var = tk.StringVar(value="Ninguna carpeta seleccionada todavía")
        tk.Label(
            path_bar,
            textvariable=self.folder_path_var,
            bg=COLORS["bg_app"],
            fg=COLORS["text_dark"],
            font=("Consolas", 10),
        ).pack(side="left", padx=(6, 0))

    def _build_progress_area(self) -> None:
        self.progress_frame = tk.Frame(self.root, bg=COLORS["bg_app"])
        inner = tk.Frame(self.progress_frame, bg=COLORS["bg_app"])
        inner.pack(fill="x", padx=20, pady=(4, 4))
        self.progress_label = tk.Label(
            inner, text="", bg=COLORS["bg_app"], fg=COLORS["text_dark"], font=("Segoe UI", 9)
        )
        self.progress_label.pack(side="left")
        self.btn_cancel_scan = ttk.Button(
            inner, text="Cancelar análisis", style="Secondary.TButton", command=self.cancel_scan, state="disabled"
        )
        self.btn_cancel_scan.pack(side="right")
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 8))
        # Not packed into the layout until a scan starts; see _show_progress().

    def _show_progress(self, show: bool) -> None:
        if show:
            self.progress_frame.pack(fill="x", before=self.cards_container)
        else:
            self.progress_frame.pack_forget()

    # ------------------------------------------------------------------
    # Dashboard cards
    # ------------------------------------------------------------------
    def _build_cards(self) -> None:
        self.cards_container = tk.Frame(self.root, bg=COLORS["bg_app"])
        self.cards_container.pack(fill="x", padx=20, pady=(6, 10))
        for i in range(4):
            self.cards_container.grid_columnconfigure(i, weight=1, uniform="cards")

        specs = [
            ("XML TOTALES", "total", COLORS["text_dark"]),
            ("EN PROCESS", "process", COLORS["accent"]),
            ("SIN PROCESAR", "unprocess", COLORS["orange"]),
            ("ESPACIO USADO", "size", COLORS["text_dark"]),
        ]
        self.card_value_vars = {}
        self.card_sub_vars = {}
        for i, (title, key, value_color) in enumerate(specs):
            card = tk.Frame(
                self.cards_container, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1
            )
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            tk.Label(
                card, text=title, bg=COLORS["card_bg"], fg=COLORS["text_muted"], font=("Segoe UI", 9, "bold")
            ).pack(anchor="w", padx=16, pady=(16, 0))
            val_var = tk.StringVar(value="—")
            tk.Label(
                card, textvariable=val_var, bg=COLORS["card_bg"], fg=value_color, font=("Segoe UI", 30, "bold")
            ).pack(anchor="w", padx=16, pady=(2, 0))
            sub_var = tk.StringVar(value="")
            tk.Label(
                card, textvariable=sub_var, bg=COLORS["card_bg"], fg=COLORS["text_muted"], font=("Segoe UI", 9)
            ).pack(anchor="w", padx=16, pady=(0, 16))
            self.card_value_vars[key] = val_var
            self.card_sub_vars[key] = sub_var

    # ------------------------------------------------------------------
    # Oldest XML panel (always visible)
    # ------------------------------------------------------------------
    def _build_info_file_panel(self, title: str, title_color: str, attr_prefix: str, get_file):
        """Build a compact 'file spotlight' card (used for both the oldest
        and the most recent XML) and store its StringVars as
        self.<attr_prefix>_file_var / _modified_var / _age_var / _size_var.
        """
        frame = tk.Frame(self.root, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1)
        frame.pack(fill="x", padx=20, pady=(0, 10))
        inner = tk.Frame(frame, bg=COLORS["card_bg"])
        inner.pack(fill="x", padx=16, pady=10)
        inner.grid_columnconfigure(0, weight=1)

        tk.Label(inner, text=title, bg=COLORS["card_bg"], fg=title_color, font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", columnspan=2
        )

        row1 = tk.Frame(inner, bg=COLORS["card_bg"])
        row1.grid(row=1, column=0, sticky="w", pady=(6, 0))

        file_var = tk.StringVar(value="-")
        modified_var = tk.StringVar(value="-")
        age_var = tk.StringVar(value="-")
        size_var = tk.StringVar(value="-")
        setattr(self, f"{attr_prefix}_file_var", file_var)
        setattr(self, f"{attr_prefix}_modified_var", modified_var)
        setattr(self, f"{attr_prefix}_age_var", age_var)
        setattr(self, f"{attr_prefix}_size_var", size_var)

        def add_field(parent, label, var, col):
            f = tk.Frame(parent, bg=COLORS["card_bg"])
            f.grid(row=0, column=col, sticky="w", padx=(0 if col == 0 else 28, 0))
            tk.Label(f, text=label, bg=COLORS["card_bg"], fg=COLORS["text_muted"], font=("Segoe UI", 8)).pack(
                anchor="w"
            )
            tk.Label(
                f, textvariable=var, bg=COLORS["card_bg"], fg=COLORS["text_dark"], font=("Segoe UI", 10, "bold")
            ).pack(anchor="w")

        add_field(row1, "Archivo", file_var, 0)
        add_field(row1, "Modificado", modified_var, 1)
        add_field(row1, "Antigüedad", age_var, 2)
        add_field(row1, "Tamaño", size_var, 3)

        ttk.Button(
            inner,
            text="📂 Abrir ubicación",
            style="Secondary.TButton",
            command=lambda: self.open_file_location(get_file().path if get_file() else ""),
        ).grid(row=1, column=1, sticky="e")

    def _build_oldest_panel(self) -> None:
        self._build_info_file_panel(
            "EL MÁS VIEJO",
            COLORS["red"],
            "oldest",
            lambda: self.scan_result.oldest if self.scan_result else None,
        )
        self._build_info_file_panel(
            "EL MÁS NUEVO (el último)",
            COLORS["accent"],
            "newest",
            lambda: self.scan_result.newest if self.scan_result else None,
        )

    # ------------------------------------------------------------------
    # Notebook
    # ------------------------------------------------------------------
    def _build_notebook(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        self.tab_projects = tk.Frame(self.notebook, bg=COLORS["bg_app"])
        self.tab_dashboard = tk.Frame(self.notebook, bg=COLORS["bg_app"])
        self.tab_advisor = tk.Frame(self.notebook, bg=COLORS["bg_app"])
        self.tab_stats = tk.Frame(self.notebook, bg=COLORS["bg_app"])

        self.notebook.add(self.tab_projects, text="  📊 Proyectos  ")
        self.notebook.add(self.tab_dashboard, text="  Tabla de Archivos  ")
        self.notebook.add(self.tab_advisor, text="  Cleanup Advisor  ")
        self.notebook.add(self.tab_stats, text="  Statistics  ")

        self._build_projects_tab(self.tab_projects)
        self._build_dashboard_tab(self.tab_dashboard)
        self._build_advisor_tab(self.tab_advisor)
        self._build_stats_tab(self.tab_stats)

    # ------------------------------------------------------------------
    # Proyectos tab: process / unprocess por carpeta de proyecto (FLX)
    # ------------------------------------------------------------------
    def _build_projects_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent, bg=COLORS["bg_app"])
        container.pack(fill="both", expand=True, pady=(14, 0))

        tk.Label(
            container,
            text="Tus proyectos",
            bg=COLORS["bg_app"],
            fg=COLORS["text_dark"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            container,
            text="Cuántos XML hay en Process y en Unprocess dentro de cada proyecto de la carpeta FLX.",
            bg=COLORS["bg_app"],
            fg=COLORS["text_muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 12))

        self.projects_empty_label = tk.Label(
            container,
            text="Selecciona tu carpeta FLX arriba para ver aquí tus proyectos. 📁",
            bg=COLORS["bg_app"],
            fg=COLORS["text_muted"],
            font=("Segoe UI", 11),
        )
        self.projects_empty_label.pack(anchor="w", pady=(20, 0))

        tree_frame = tk.Frame(container, bg=COLORS["bg_app"])
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        self.projects_tree_frame = tree_frame

        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        columns = ("project", "process", "unprocess", "total", "size")
        self.projects_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", yscrollcommand=vsb.set, selectmode="browse", height=18
        )
        vsb.config(command=self.projects_tree.yview)
        headings = {
            "project": "Proyecto",
            "process": "En Process",
            "unprocess": "Sin Procesar",
            "total": "Total XML",
            "size": "Espacio",
        }
        widths = {"project": 260, "process": 140, "unprocess": 140, "total": 120, "size": 120}
        for col in columns:
            self.projects_tree.heading(col, text=headings[col])
            self.projects_tree.column(
                col, width=widths[col], anchor=("w" if col == "project" else "center"), stretch=(col == "project")
            )
        self.projects_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.projects_tree.bind(
            "<Double-1>", lambda e: self._open_path(self.projects_tree.identify_row(e.y))
        )

        self.projects_hint_label = tk.Label(
            container,
            text="Doble clic en un proyecto para abrir su carpeta.",
            bg=COLORS["bg_app"],
            fg=COLORS["text_muted"],
            font=("Segoe UI", 8),
        )

    # ------------------------------------------------------------------
    # Dashboard tab: filters, search, table
    # ------------------------------------------------------------------
    def _build_dashboard_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent, bg=COLORS["bg_app"])
        container.pack(fill="both", expand=True, pady=(10, 0))

        filters = tk.Frame(container, bg=COLORS["bg_app"])
        filters.pack(fill="x", pady=(0, 6))
        tk.Label(filters, text="Filtro:", bg=COLORS["bg_app"], font=("Segoe UI", 9)).pack(side="left")
        self.filter_var = tk.StringVar(value="Todos")
        filter_combo = ttk.Combobox(
            filters, textvariable=self.filter_var, values=FILTER_OPTIONS, state="readonly", width=18
        )
        filter_combo.pack(side="left", padx=(6, 16))
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters_and_search())

        tk.Label(filters, text="Desde:", bg=COLORS["bg_app"], font=("Segoe UI", 9)).pack(side="left")
        self.date_from_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.date_from_var, width=10).pack(side="left", padx=(4, 10))
        tk.Label(filters, text="Hasta:", bg=COLORS["bg_app"], font=("Segoe UI", 9)).pack(side="left")
        self.date_to_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.date_to_var, width=10).pack(side="left", padx=(4, 10))
        ttk.Button(
            filters, text="Aplicar", style="Secondary.TButton", command=self._apply_filters_and_search
        ).pack(side="left")
        tk.Label(
            filters, text="(DD/MM/AAAA)", bg=COLORS["bg_app"], fg=COLORS["text_muted"], font=("Segoe UI", 7)
        ).pack(side="left", padx=(6, 0))

        search_frame = tk.Frame(container, bg=COLORS["bg_app"])
        search_frame.pack(fill="x", pady=(0, 8))
        tk.Label(search_frame, text="🔎", bg=COLORS["bg_app"]).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(4, 10))
        self._add_placeholder(self.search_entry, self.search_var, self._search_placeholder)
        self.search_var.trace_add("write", lambda *a: self._on_search_change())
        self.results_count_label = tk.Label(
            search_frame, text="0 archivo(s)", bg=COLORS["bg_app"], fg=COLORS["text_muted"], font=("Segoe UI", 9)
        )
        self.results_count_label.pack(side="right")

        tree_frame = tk.Frame(container, bg=COLORS["bg_app"])
        tree_frame.pack(fill="both", expand=True)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=TREE_COLUMNS,
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode="browse",
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        for col in TREE_COLUMNS:
            self.tree.heading(col, text=TREE_HEADINGS[col], command=lambda c=col: self._on_heading_click(c))
            self.tree.column(col, width=TREE_WIDTHS[col], anchor="w", stretch=(col == "path"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.tag_configure("status_recent", background="#eafaf1")
        self.tree.tag_configure("status_review", background="#fef9e7")
        self.tree.tag_configure("status_old", background="#fdf0e4")
        self.tree.tag_configure("status_very_old", background="#fdecea")

        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self._update_heading_indicators()

    def _add_placeholder(self, entry: ttk.Entry, var: tk.StringVar, placeholder: str) -> None:
        var.set(placeholder)
        entry.configure(foreground=COLORS["text_muted"])

        def on_focus_in(_event):
            if var.get() == placeholder:
                var.set("")
                entry.configure(foreground=COLORS["text_dark"])

        def on_focus_out(_event):
            if not var.get():
                var.set(placeholder)
                entry.configure(foreground=COLORS["text_muted"])

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    # ------------------------------------------------------------------
    # Cleanup Advisor tab
    # ------------------------------------------------------------------
    def _build_advisor_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent, bg=COLORS["bg_app"])
        container.pack(fill="both", expand=True, pady=(10, 0))

        tk.Label(
            container, text="Cleanup Advisor", bg=COLORS["bg_app"], fg=COLORS["text_dark"], font=("Segoe UI", 13, "bold")
        ).pack(anchor="w")
        tk.Label(
            container,
            text="Las recomendaciones se basan solo en antigüedad, fecha de modificación y tamaño. Ningún XML se elimina automáticamente.",
            bg=COLORS["bg_app"],
            fg=COLORS["text_muted"],
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(0, 10))

        sim_frame = tk.Frame(
            container, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1
        )
        sim_frame.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(sim_frame, bg=COLORS["card_bg"])
        inner.pack(fill="x", padx=16, pady=14)

        row1 = tk.Frame(inner, bg=COLORS["card_bg"])
        row1.pack(fill="x")
        tk.Label(
            row1, text="Conservar XML de los últimos:", bg=COLORS["card_bg"], font=("Segoe UI", 10, "bold")
        ).pack(side="left")
        self.retention_var = tk.StringVar(value=self._retention_label_for_days(self.settings.get("retention_days", 30)))
        retention_combo = ttk.Combobox(
            row1, textvariable=self.retention_var, values=RETENTION_OPTIONS, state="readonly", width=14
        )
        retention_combo.pack(side="left", padx=(8, 8))
        retention_combo.bind("<<ComboboxSelected>>", self._on_retention_change)

        self.custom_days_var = tk.StringVar(value=str(self.settings.get("retention_days", 30)))
        self.custom_days_spin = ttk.Spinbox(
            row1, from_=0, to=3650, textvariable=self.custom_days_var, width=6, command=self._on_retention_change
        )
        self.custom_days_spin.bind("<Return>", lambda e: self._on_retention_change())
        if self.retention_var.get() == "Personalizado":
            self.custom_days_spin.pack(side="left")

        row2 = tk.Frame(inner, bg=COLORS["card_bg"])
        row2.pack(fill="x", pady=(14, 0))

        def sim_field(parent, label, var, col):
            f = tk.Frame(parent, bg=COLORS["card_bg"])
            f.grid(row=0, column=col, sticky="w", padx=(0 if col == 0 else 30, 0))
            tk.Label(f, text=label, bg=COLORS["card_bg"], fg=COLORS["text_muted"], font=("Segoe UI", 8)).pack(
                anchor="w"
            )
            tk.Label(
                f, textvariable=var, bg=COLORS["card_bg"], fg=COLORS["text_dark"], font=("Segoe UI", 14, "bold")
            ).pack(anchor="w")

        self.sim_kept_var = tk.StringVar(value="—")
        self.sim_candidates_var = tk.StringVar(value="—")
        self.sim_kept_size_var = tk.StringVar(value="—")
        self.sim_candidates_size_var = tk.StringVar(value="—")
        sim_field(row2, "XML conservados", self.sim_kept_var, 0)
        sim_field(row2, "XML candidatos a limpieza", self.sim_candidates_var, 1)
        sim_field(row2, "Espacio conservado", self.sim_kept_size_var, 2)
        sim_field(row2, "Espacio potencialmente recuperable", self.sim_candidates_size_var, 3)

        row3 = tk.Frame(inner, bg=COLORS["card_bg"])
        row3.pack(fill="x", pady=(16, 0))
        ttk.Button(
            row3, text="🔍 Analizar limpieza", style="Accent.TButton", command=self.analyze_cleanup_dialog
        ).pack(side="left")
        ttk.Button(
            row3, text="🧹 Limpiar XML antiguos", style="Danger.TButton", command=self.start_cleanup_flow
        ).pack(side="left", padx=(10, 0))

        row4 = tk.Frame(inner, bg=COLORS["card_bg"])
        row4.pack(fill="x", pady=(12, 0))
        self.safe_mode = tk.BooleanVar(value=self.settings.get("safe_mode", True))
        ttk.Checkbutton(
            row4,
            text="SAFE MODE (nunca eliminar, solo mover)",
            variable=self.safe_mode,
            style="Card.TCheckbutton",
            command=self._on_safe_mode_change,
        ).pack(side="left")
        self.move_instead = tk.BooleanVar(value=self.settings.get("move_instead_of_delete", True))
        ttk.Checkbutton(
            row4,
            text="Mover archivos en lugar de eliminar",
            variable=self.move_instead,
            style="Card.TCheckbutton",
            command=self._on_move_instead_change,
        ).pack(side="left", padx=(20, 0))

        panels = tk.Frame(container, bg=COLORS["bg_app"])
        panels.pack(fill="both", expand=True, pady=(4, 0))
        panels.grid_columnconfigure(0, weight=1)
        panels.grid_columnconfigure(1, weight=1)
        panels.grid_rowconfigure(0, weight=1)

        left = tk.Frame(panels, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(left, text="10 Oldest XML Files", bg=COLORS["card_bg"], font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        self.top10_tree = ttk.Treeview(left, columns=("rank_name", "age"), show="headings", height=10)
        self.top10_tree.heading("rank_name", text="Archivo")
        self.top10_tree.heading("age", text="Antigüedad")
        self.top10_tree.column("rank_name", width=260, anchor="w")
        self.top10_tree.column("age", width=90, anchor="center")
        self.top10_tree.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.top10_tree.bind(
            "<Double-1>", lambda e: self.open_file_location(self.top10_tree.identify_row(e.y))
        )

        right = tk.Frame(panels, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        tk.Label(right, text="Folder Cleanup Ranking", bg=COLORS["card_bg"], font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        self.ranking_empty_label = tk.Label(
            right,
            text="Selecciona tu carpeta FLX para ver aquí qué carpeta tiene más espacio para liberar.",
            bg=COLORS["card_bg"],
            fg=COLORS["text_muted"],
            font=("Segoe UI", 9),
            wraplength=300,
            justify="left",
        )
        self.ranking_empty_label.pack(anchor="w", padx=12, pady=(0, 10))
        self.ranking_tree = ttk.Treeview(right, columns=("folder", "count", "reclaimable"), show="headings", height=10)
        self.ranking_tree.heading("folder", text="Carpeta")
        self.ranking_tree.heading("count", text="XML")
        self.ranking_tree.heading("reclaimable", text="Recuperable")
        self.ranking_tree.column("folder", width=160, anchor="w")
        self.ranking_tree.column("count", width=70, anchor="center")
        self.ranking_tree.column("reclaimable", width=100, anchor="e")
        self.ranking_tree.bind(
            "<Double-1>", lambda e: self._open_ranking_folder(self.ranking_tree.identify_row(e.y))
        )

    # ------------------------------------------------------------------
    # Statistics tab
    # ------------------------------------------------------------------
    def _build_stats_tab(self, parent: tk.Frame) -> None:
        container = tk.Frame(parent, bg=COLORS["bg_app"])
        container.pack(fill="both", expand=True, pady=(10, 0))

        top = tk.Frame(container, bg=COLORS["bg_app"])
        top.pack(fill="x")
        for i in range(3):
            top.grid_columnconfigure(i, weight=1, uniform="stats_top")

        summary_card = tk.Frame(top, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1)
        summary_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(summary_card, text="Summary", font=("Segoe UI", 10, "bold"), bg=COLORS["card_bg"]).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        self.stats_labels = {}
        for key, label in [
            ("total_xml", "Total XML"),
            ("total_size", "Total size"),
            ("oldest", "Oldest XML"),
            ("newest", "Newest XML"),
            ("avg_size", "Average XML size"),
        ]:
            row = tk.Frame(summary_card, bg=COLORS["card_bg"])
            row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text=label + ":", bg=COLORS["card_bg"], fg=COLORS["text_muted"], font=("Segoe UI", 9)).pack(
                side="left"
            )
            var = tk.StringVar(value="—")
            tk.Label(row, textvariable=var, bg=COLORS["card_bg"], fg=COLORS["text_dark"], font=("Segoe UI", 9, "bold")).pack(
                side="right"
            )
            self.stats_labels[key] = var
        tk.Frame(summary_card, bg=COLORS["card_bg"], height=8).pack()

        growth_card = tk.Frame(top, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1)
        growth_card.grid(row=0, column=1, sticky="nsew", padx=8)
        tk.Label(
            growth_card, text="Folder Growth Analysis (approx.)", font=("Segoe UI", 10, "bold"), bg=COLORS["card_bg"]
        ).pack(anchor="w", padx=12, pady=(10, 4))
        self.growth_labels = {}
        for key, label in [
            ("per_day", "Promedio / día"),
            ("per_hour", "≈ por hora"),
            ("per_minute", "≈ por minuto"),
            ("now", "Actualmente"),
            ("plus1", "+1 día"),
            ("plus7", "+7 días"),
            ("plus30", "+30 días"),
        ]:
            row = tk.Frame(growth_card, bg=COLORS["card_bg"])
            row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text=label + ":", bg=COLORS["card_bg"], fg=COLORS["text_muted"], font=("Segoe UI", 9)).pack(
                side="left"
            )
            var = tk.StringVar(value="—")
            tk.Label(row, textvariable=var, bg=COLORS["card_bg"], fg=COLORS["text_dark"], font=("Segoe UI", 9, "bold")).pack(
                side="right"
            )
            self.growth_labels[key] = var
        tk.Frame(growth_card, bg=COLORS["card_bg"], height=8).pack()

        health_card = tk.Frame(top, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1)
        health_card.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        tk.Label(health_card, text="Folder Health", font=("Segoe UI", 10, "bold"), bg=COLORS["card_bg"]).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        self.health_status_var = tk.StringVar(value="—")
        self.health_status_label = tk.Label(
            health_card,
            textvariable=self.health_status_var,
            bg=COLORS["card_bg"],
            fg=COLORS["text_dark"],
            font=("Segoe UI", 16, "bold"),
        )
        self.health_status_label.pack(anchor="w", padx=12, pady=(0, 4))
        self.health_reasons_var = tk.StringVar(value="")
        tk.Label(
            health_card,
            textvariable=self.health_reasons_var,
            bg=COLORS["card_bg"],
            fg=COLORS["text_muted"],
            font=("Segoe UI", 8),
            justify="left",
            wraplength=260,
        ).pack(anchor="w", padx=12, pady=(0, 10))

        bottom = tk.Frame(container, bg=COLORS["bg_app"])
        bottom.pack(fill="both", expand=True, pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)
        bottom.grid_rowconfigure(0, weight=1)

        chart_card = tk.Frame(bottom, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1)
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(chart_card, text="XML generados por día", font=("Segoe UI", 10, "bold"), bg=COLORS["card_bg"]).pack(
            anchor="w", padx=12, pady=(10, 4)
        )
        self.chart_label = tk.Label(chart_card, bg=COLORS["card_bg"], text="Sin datos todavía.", fg=COLORS["text_muted"])
        self.chart_label.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        table_card = tk.Frame(bottom, bg=COLORS["card_bg"], highlightbackground=COLORS["border"], highlightthickness=1)
        table_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        header_row = tk.Frame(table_card, bg=COLORS["card_bg"])
        header_row.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(header_row, text="Archivos por periodo", font=("Segoe UI", 10, "bold"), bg=COLORS["card_bg"]).pack(
            side="left"
        )
        self.group_var = tk.StringVar(value="Día")
        group_combo = ttk.Combobox(
            header_row, textvariable=self.group_var, values=["Día", "Semana", "Mes"], state="readonly", width=10
        )
        group_combo.pack(side="right")
        group_combo.bind("<<ComboboxSelected>>", lambda e: self._update_period_table())
        self.period_tree = ttk.Treeview(table_card, columns=("period", "count"), show="headings", height=12)
        self.period_tree.heading("period", text="Periodo")
        self.period_tree.heading("count", text="XML")
        self.period_tree.column("period", width=140, anchor="w")
        self.period_tree.column("count", width=80, anchor="center")
        self.period_tree.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ------------------------------------------------------------------
    # Folder selection & scanning
    # ------------------------------------------------------------------
    def select_folder(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta FLX")
        if not path:
            return
        self.current_folder = path
        self.folder_path_var.set(path)
        self.settings["last_folder"] = path
        config.save_settings(self.settings)
        self.btn_rescan.config(state="normal")
        self.start_scan()

    def start_scan(self) -> None:
        if self.scanning:
            return
        if not self.current_folder or not os.path.isdir(self.current_folder):
            messagebox.showerror("Carpeta inválida", "La carpeta seleccionada no existe o no es accesible.")
            return

        self.scanning = True
        self.cancel_event = threading.Event()
        self._set_status_scanning()
        self._show_progress(True)
        self.progress_bar["value"] = 0
        self.progress_label.config(text="Scanning XML files...")
        self.btn_select.config(state="disabled")
        self.btn_rescan.config(state="disabled")
        self.btn_cancel_scan.config(state="normal")

        include_sub = True  # FLX projects nest process/unprocess XML two levels deep.
        settings_copy = dict(self.settings)
        folder = self.current_folder
        cancel_event = self.cancel_event

        thread = threading.Thread(
            target=self._scan_worker, args=(folder, settings_copy, include_sub, cancel_event), daemon=True
        )
        thread.start()
        self.root.after(80, self._poll_scan_queue)

    def _scan_worker(self, folder: str, settings: dict, include_sub: bool, cancel_event: threading.Event) -> None:
        def progress_cb(done: int, total: Optional[int]) -> None:
            self.scan_queue.put(("progress", done, total))

        try:
            result = scanner.scan_folder(
                folder,
                settings,
                include_subfolders=include_sub,
                progress_callback=progress_cb,
                cancel_event=cancel_event,
            )
            self.scan_queue.put(("done", result))
        except Exception as exc:  # noqa: BLE001 - background thread must never crash silently
            logger.exception("Unexpected scan error")
            self.scan_queue.put(("error", str(exc)))

    def _poll_scan_queue(self) -> None:
        try:
            while True:
                item = self.scan_queue.get_nowait()
                kind = item[0]
                if kind == "progress":
                    self._update_scan_progress(item[1], item[2])
                elif kind == "done":
                    self._on_scan_complete(item[1])
                    return
                elif kind == "error":
                    self._on_scan_error(item[1])
                    return
        except queue.Empty:
            pass
        if self.scanning:
            self.root.after(80, self._poll_scan_queue)

    def _update_scan_progress(self, done: int, total: Optional[int]) -> None:
        total = total or 0
        pct = int((done / total) * 100) if total else 0
        self.progress_bar["maximum"] = max(total, 1)
        self.progress_bar["value"] = done
        self.progress_label.config(text=f"Scanning XML files... {done:,} / {total:,}    {pct}%")

    def _on_scan_complete(self, result: ScanResult) -> None:
        self.scanning = False
        self.scan_result = result
        self.all_files = result.files
        self._show_progress(False)
        self.btn_select.config(state="normal")
        self.btn_rescan.config(state="normal")
        self.btn_cancel_scan.config(state="disabled")

        if result.cancelled:
            self._set_status_ready(note="ANÁLISIS CANCELADO", color=COLORS["orange"])
            messagebox.showinfo(
                "Análisis cancelado",
                f"El análisis fue cancelado. Se procesaron {len(result.files):,} archivo(s) antes de cancelar.",
            )
        else:
            self._set_status_ready()
            if not result.errors and result.total_count == 0:
                messagebox.showinfo(
                    "Sin archivos XML",
                    "No se encontraron archivos .xml en la carpeta seleccionada.",
                )

        if result.errors:
            logger.warning("Scan completed with %d error(s)", len(result.errors))

        api_state.update(self.current_folder, result, self.settings)
        self._refresh_all_views()

    def _on_scan_error(self, message: str) -> None:
        self.scanning = False
        self._show_progress(False)
        self.btn_select.config(state="normal")
        self.btn_rescan.config(state="normal" if self.current_folder else "disabled")
        self.btn_cancel_scan.config(state="disabled")
        self._set_status_ready(note="ERROR", color=COLORS["red"])
        messagebox.showerror("Error de análisis", f"Ocurrió un error inesperado durante el análisis:\n{message}")

    def cancel_scan(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.btn_cancel_scan.config(state="disabled")

    # ------------------------------------------------------------------
    # Status indicator
    # ------------------------------------------------------------------
    def _set_status_scanning(self) -> None:
        self.status_dot.configure(fg=COLORS["orange"])
        self.status_text.configure(text="SCANNING...")

    def _set_status_ready(self, note: Optional[str] = None, color: Optional[str] = None) -> None:
        self.status_dot.configure(fg=color or COLORS["green"])
        self.status_text.configure(text=note or "SYSTEM READY")

    # ------------------------------------------------------------------
    # View refresh
    # ------------------------------------------------------------------
    def _refresh_all_views(self) -> None:
        self._update_dashboard_cards()
        self._update_oldest_panel()
        self._update_projects_tab()
        self._apply_filters_and_search()
        self._update_top10()
        self._update_subfolder_ranking()
        self._update_cleanup_simulation()
        self._update_statistics_tab()

    def _update_projects_tab(self) -> None:
        projects = self.scan_result.projects if self.scan_result else []
        self.projects_tree.delete(*self.projects_tree.get_children())

        if not projects:
            self.projects_tree_frame.pack_forget()
            self.projects_hint_label.pack_forget()
            self.projects_empty_label.pack(anchor="w", pady=(20, 0))
            return

        self.projects_empty_label.pack_forget()
        self.projects_tree_frame.pack(fill="both", expand=True, pady=(0, 6))
        self.projects_hint_label.pack(anchor="w")

        for p in projects:
            iid = str(Path(self.current_folder) / p.name) if p.name != "(raíz)" else self.current_folder
            try:
                self.projects_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        p.name,
                        f"{p.process_count:,}",
                        f"{p.unprocess_count:,}",
                        f"{p.total_count:,}",
                        format_size(p.total_bytes),
                    ),
                )
            except tk.TclError:
                continue

    def _get_current_retention_days(self) -> int:
        sel = self.retention_var.get()
        if sel == "Personalizado":
            try:
                return max(0, int(self.custom_days_var.get()))
            except ValueError:
                return int(self.settings.get("retention_days", 30))
        return RETENTION_DAYS_MAP.get(sel, int(self.settings.get("retention_days", 30)))

    def _retention_label_for_days(self, days: int) -> str:
        return REV_RETENTION_MAP.get(days, "Personalizado")

    def _update_dashboard_cards(self) -> None:
        total = len(self.all_files)
        self.card_value_vars["total"].set(f"{total:,}")
        n_projects = len(self.scan_result.projects) if self.scan_result else 0
        self.card_sub_vars["total"].set(f"en {n_projects:,} proyecto(s)" if n_projects else "")

        total_process = self.scan_result.total_process if self.scan_result else 0
        total_unprocess = self.scan_result.total_unprocess if self.scan_result else 0
        self.card_value_vars["process"].set(f"{total_process:,}")
        self.card_value_vars["unprocess"].set(f"{total_unprocess:,}")
        if total:
            self.card_sub_vars["process"].set(f"{total_process / total * 100:.0f}% del total")
            self.card_sub_vars["unprocess"].set(f"{total_unprocess / total * 100:.0f}% del total")
        else:
            self.card_sub_vars["process"].set("")
            self.card_sub_vars["unprocess"].set("")

        total_size = self.scan_result.total_size_bytes if self.scan_result else 0
        self.card_value_vars["size"].set(format_size(total_size))
        self.card_sub_vars["size"].set("")

    def _update_info_file_panel(self, attr_prefix: str, info: Optional[XMLFileInfo]) -> None:
        file_var = getattr(self, f"{attr_prefix}_file_var")
        modified_var = getattr(self, f"{attr_prefix}_modified_var")
        age_var = getattr(self, f"{attr_prefix}_age_var")
        size_var = getattr(self, f"{attr_prefix}_size_var")
        if not info:
            file_var.set("-")
            modified_var.set("-")
            age_var.set("-")
            size_var.set("-")
            return
        file_var.set(info.name)
        modified_var.set(info.modified.strftime("%Y-%m-%d %H:%M:%S"))
        age_var.set(f"{int(info.age_days):,} días")
        size_var.set(info.size_display)

    def _update_oldest_panel(self) -> None:
        self._update_info_file_panel("oldest", self.scan_result.oldest if self.scan_result else None)
        self._update_info_file_panel("newest", self.scan_result.newest if self.scan_result else None)

    # ------------------------------------------------------------------
    # Filtering / search / sort / table population
    # ------------------------------------------------------------------
    def _on_search_change(self) -> None:
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
        self._search_after_id = self.root.after(250, self._apply_filters_and_search)

    def _parse_date(self, text: str):
        text = text.strip()
        if not text:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _apply_filters_and_search(self) -> None:
        files = list(self.all_files)
        now = datetime.now()
        filt = self.filter_var.get() if hasattr(self, "filter_var") else "Todos"

        if filt == "Hoy":
            files = [f for f in files if f.modified.date() == now.date()]
        elif filt == "Últimas 24 horas":
            files = [f for f in files if f.age_days < 1]
        elif filt == "Últimos 7 días":
            files = [f for f in files if f.age_days < 7]
        elif filt == "Últimos 30 días":
            files = [f for f in files if f.age_days < 30]
        elif filt == "Más de 30 días":
            files = [f for f in files if f.age_days > 30]
        elif filt == "Más de 60 días":
            files = [f for f in files if f.age_days > 60]
        elif filt == "Más de 90 días":
            files = [f for f in files if f.age_days > 90]

        date_from = self._parse_date(self.date_from_var.get()) if hasattr(self, "date_from_var") else None
        date_to = self._parse_date(self.date_to_var.get()) if hasattr(self, "date_to_var") else None
        if date_from:
            files = [f for f in files if f.modified.date() >= date_from]
        if date_to:
            files = [f for f in files if f.modified.date() <= date_to]

        query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        if query and query != self._search_placeholder.lower():
            files = [f for f in files if query in f.name.lower() or query in f.path.lower()]

        files = self._sort_files(files)
        self.filtered_files = files
        self._populate_tree(files)
        if hasattr(self, "results_count_label"):
            self.results_count_label.config(text=f"{len(files):,} archivo(s)")

    def _sort_files(self, files: List[XMLFileInfo]) -> List[XMLFileInfo]:
        key = SORT_KEYS.get(self.sort_column, SORT_KEYS["modified"])
        return sorted(files, key=key, reverse=self.sort_reverse)

    def _on_heading_click(self, col: str) -> None:
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False
        self._update_heading_indicators()
        self._apply_filters_and_search()

    def _update_heading_indicators(self) -> None:
        for col, text in TREE_HEADINGS.items():
            suffix = ""
            if col == self.sort_column:
                suffix = " ▼" if self.sort_reverse else " ▲"
            self.tree.heading(col, text=text + suffix)

    def _populate_tree(self, files: List[XMLFileInfo]) -> None:
        self._tree_generation += 1
        gen = self._tree_generation
        self.tree.delete(*self.tree.get_children())
        self._populate_chunk(files, 0, gen)

    def _populate_chunk(self, files: List[XMLFileInfo], index: int, gen: int, chunk_size: int = 1500) -> None:
        if gen != self._tree_generation:
            return
        end = min(index + chunk_size, len(files))
        for f in files[index:end]:
            tag = STATUS_TAGS.get(f.status, "status_recent")
            values = (
                f.name,
                f.created.strftime("%Y-%m-%d %H:%M:%S"),
                f.modified.strftime("%Y-%m-%d %H:%M:%S"),
                f.age_display,
                f.size_display,
                f.path,
                f.status,
                f.recommendation,
            )
            self.tree.insert("", "end", iid=f.path, values=values, tags=(tag,))
        if end < len(files) and gen == self._tree_generation:
            self.root.after(1, lambda: self._populate_chunk(files, end, gen, chunk_size))

    def _on_tree_double_click(self, event) -> None:
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.open_file_location(item_id)

    # ------------------------------------------------------------------
    # Top 10 oldest / folder ranking
    # ------------------------------------------------------------------
    def _update_top10(self) -> None:
        top10 = sorted(self.all_files, key=lambda f: f.age_days, reverse=True)[:10]
        self.top10_tree.delete(*self.top10_tree.get_children())
        for i, f in enumerate(top10, start=1):
            self.top10_tree.insert("", "end", iid=f.path, values=(f"{i}. {f.name}", f.age_display))

    def _update_subfolder_ranking(self) -> None:
        breakdown = self.scan_result.subfolder_breakdown if self.scan_result else {}
        self.ranking_tree.delete(*self.ranking_tree.get_children())
        if not breakdown:
            self.ranking_tree.pack_forget()
            self.ranking_empty_label.pack(anchor="w", padx=12, pady=(0, 10))
            return
        self.ranking_empty_label.pack_forget()
        self.ranking_tree.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        ranked = sorted(breakdown.items(), key=lambda kv: kv[1]["reclaimable_bytes"], reverse=True)
        for name, data in ranked:
            iid = name if name == "(root)" else str(Path(self.current_folder) / name)
            try:
                self.ranking_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(name, f"{int(data['count']):,}", format_size(int(data["reclaimable_bytes"]))),
                )
            except tk.TclError:
                continue

    def _open_ranking_folder(self, item_id: str) -> None:
        if not item_id:
            return
        target = self.current_folder if item_id == "(root)" else item_id
        self._open_path(target)

    # ------------------------------------------------------------------
    # Cleanup simulation (live, no rescan required)
    # ------------------------------------------------------------------
    def _on_retention_change(self, event=None) -> None:
        if self.retention_var.get() == "Personalizado":
            self.custom_days_spin.pack(side="left")
        else:
            self.custom_days_spin.pack_forget()
        days = self._get_current_retention_days()
        self.settings["retention_days"] = days
        config.save_settings(self.settings)
        self._reclassify_all_files()
        self._update_dashboard_cards()
        self._update_cleanup_simulation()
        self._apply_filters_and_search()

    def _update_cleanup_simulation(self) -> None:
        if not self.all_files:
            self.sim_kept_var.set("—")
            self.sim_candidates_var.set("—")
            self.sim_kept_size_var.set("—")
            self.sim_candidates_size_var.set("—")
            return
        retention = self._get_current_retention_days()
        sim = cleanup.simulate_cleanup(self.all_files, retention)
        self.sim_kept_var.set(f"{sim.kept_count:,}")
        self.sim_candidates_var.set(f"{sim.candidate_count:,}")
        self.sim_kept_size_var.set(sim.kept_size_display)
        self.sim_candidates_size_var.set(sim.candidate_size_display)

    def _on_safe_mode_change(self) -> None:
        self.settings["safe_mode"] = self.safe_mode.get()
        config.save_settings(self.settings)

    def _on_move_instead_change(self) -> None:
        self.settings["move_instead_of_delete"] = self.move_instead.get()
        config.save_settings(self.settings)

    def _reclassify_all_files(self) -> None:
        for f in self.all_files:
            status, color = scanner.classify_status(f.age_days, self.settings)
            f.status = status
            f.color = color
            f.recommendation = scanner.recommend(f.age_days, f.size_bytes, self.settings)
        if self.scan_result:
            self.scan_result.age_groups = scanner.calculate_age_groups(self.all_files)
        api_state.update(self.current_folder, self.scan_result, self.settings)

    # ------------------------------------------------------------------
    # Statistics tab refresh
    # ------------------------------------------------------------------
    def _update_statistics_tab(self) -> None:
        if not self.all_files:
            for var in self.stats_labels.values():
                var.set("—")
            for var in self.growth_labels.values():
                var.set("—")
            self.health_status_var.set("—")
            self.health_status_label.configure(fg=COLORS["text_dark"])
            self.health_reasons_var.set("")
            self.chart_label.configure(image="", text="Sin datos todavía.")
            self.chart_label.image = None
            self.period_tree.delete(*self.period_tree.get_children())
            return

        st = stats_module.compute_statistics(self.all_files)
        self.stats_labels["total_xml"].set(f"{st['total_xml']:,}")
        self.stats_labels["total_size"].set(st["total_size_display"])
        self.stats_labels["oldest"].set(f"{st['oldest_age_days']:,} days")
        self.stats_labels["newest"].set(st["newest_age_display"])
        self.stats_labels["avg_size"].set(st["average_size_display"])

        growth = stats_module.compute_growth(self.all_files)
        self.growth_labels["per_day"].set(f"≈ {growth['avg_files_per_day']:,.0f} XML/día")
        self.growth_labels["per_hour"].set(f"≈ {growth['avg_files_per_hour']:,.1f} XML/hora")
        self.growth_labels["per_minute"].set(f"≈ {growth['avg_files_per_minute']:,.2f} XML/minuto")
        self.growth_labels["now"].set(growth["current_size_display"])
        self.growth_labels["plus1"].set(f"≈ {growth['projected_1d_display']}")
        self.growth_labels["plus7"].set(f"≈ {growth['projected_7d_display']}")
        self.growth_labels["plus30"].set(f"≈ {growth['projected_30d_display']}")

        health_status, reasons = stats_module.compute_health(self.all_files, self.settings)
        self.health_status_var.set(health_status)
        color = {"HEALTHY": COLORS["green"], "WARNING": COLORS["orange"], "CRITICAL": COLORS["red"]}.get(
            health_status, COLORS["text_dark"]
        )
        self.health_status_label.configure(fg=color)
        self.health_reasons_var.set("\n".join(f"• {r}" for r in reasons))

        chart_path = str(config.DATA_DIR / "chart_cache.png")
        result_path = stats_module.generate_trend_chart(self.all_files, chart_path)
        if result_path and os.path.exists(result_path):
            try:
                img = tk.PhotoImage(file=result_path)
                self.chart_label.configure(image=img, text="")
                self.chart_label.image = img
            except tk.TclError:
                self.chart_label.configure(image="", text="Gráfico no disponible.")
                self.chart_label.image = None
        else:
            self.chart_label.configure(
                image="", text="Gráfico no disponible (instala matplotlib para habilitarlo)."
            )
            self.chart_label.image = None

        self._update_period_table()

    def _update_period_table(self) -> None:
        if not self.all_files:
            self.period_tree.delete(*self.period_tree.get_children())
            return
        st = stats_module.compute_statistics(self.all_files)
        mapping = {"Día": st["by_day"], "Semana": st["by_week"], "Mes": st["by_month"]}
        data = mapping.get(self.group_var.get(), st["by_day"])
        self.period_tree.delete(*self.period_tree.get_children())
        for period in sorted(data.keys(), reverse=True):
            self.period_tree.insert("", "end", values=(period, f"{data[period]:,}"))

    # ------------------------------------------------------------------
    # Open file / folder location
    # ------------------------------------------------------------------
    def open_file_location(self, path: str) -> None:
        if not path or not os.path.exists(path):
            messagebox.showwarning("Archivo no encontrado", "El archivo ya no existe en esa ubicación.")
            return
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not open file location: %s", exc)
            messagebox.showerror("Error", f"No se pudo abrir la ubicación:\n{exc}")

    def _open_path(self, path: str) -> None:
        if not path or not os.path.exists(path):
            messagebox.showwarning("Carpeta no encontrada", "La carpeta ya no existe en esa ubicación.")
            return
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not open folder: %s", exc)
            messagebox.showerror("Error", f"No se pudo abrir la carpeta:\n{exc}")

    # ------------------------------------------------------------------
    # Generic dialog helpers
    # ------------------------------------------------------------------
    def _center_window(self, win: tk.Toplevel) -> None:
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _show_text_dialog(self, title: str, text: str) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg=COLORS["card_bg"])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(
            dlg,
            text=text,
            justify="left",
            anchor="w",
            bg=COLORS["card_bg"],
            fg=COLORS["text_dark"],
            font=("Segoe UI", 10),
            padx=24,
            pady=20,
        ).pack()
        ttk.Button(dlg, text="Cerrar", style="Accent.TButton", command=dlg.destroy).pack(pady=(0, 16))
        self._center_window(dlg)

    # ------------------------------------------------------------------
    # Analyze cleanup (read-only diagnostic)
    # ------------------------------------------------------------------
    def analyze_cleanup_dialog(self) -> None:
        if not self.all_files:
            messagebox.showinfo("Sin datos", "Primero selecciona y analiza una carpeta.")
            return
        retention = self._get_current_retention_days()
        summary = cleanup.analyze_cleanup(self.all_files, retention)
        text = (
            "DIAGNÓSTICO DE LIMPIEZA\n\n"
            f"XML encontrados:\n{summary['total_found']:,}\n\n"
            f"XML que se conservarían:\n{summary['would_keep']:,}\n\n"
            f"XML candidatos a limpieza:\n{summary['candidates']:,}\n\n"
            f"Archivo más antiguo:\n{summary['oldest_name']}\n\n"
            f"Antigüedad máxima:\n{summary['oldest_age_days']:,} días\n\n"
            f"Espacio potencialmente recuperable:\n{summary['reclaimable_display']}"
        )
        self._show_text_dialog("Análisis de limpieza", text)
        logger.info(
            "Cleanup simulation: retention=%d kept=%d candidates=%d",
            retention,
            summary["would_keep"],
            summary["candidates"],
        )

    # ------------------------------------------------------------------
    # Safe cleanup flow (multi-step confirmation)
    # ------------------------------------------------------------------
    def start_cleanup_flow(self) -> None:
        if not self.all_files:
            messagebox.showinfo("Sin datos", "Primero selecciona y analiza una carpeta.")
            return
        retention = self._get_current_retention_days()
        candidates = cleanup.get_cleanup_candidates(self.all_files, retention)
        if not candidates:
            messagebox.showinfo(
                "Sin candidatos", "No se encontraron archivos que cumplan el criterio de limpieza seleccionado."
            )
            return
        total_bytes = sum(f.size_bytes for f in candidates)
        self._show_step1_dialog(candidates, total_bytes)

    def _show_step1_dialog(self, candidates: List[XMLFileInfo], total_bytes: int) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Atención")
        dlg.configure(bg=COLORS["card_bg"])
        dlg.resizable(False, False)
        dlg.transient(self.root)

        text = (
            "ATENCIÓN\n\n"
            f"Se encontraron {len(candidates):,} archivos que cumplen\n"
            "los criterios seleccionados.\n\n"
            f"Espacio:\n{format_size(total_bytes)}\n\n"
            "¿Deseas continuar?"
        )
        tk.Label(
            dlg, text=text, justify="center", bg=COLORS["card_bg"], fg=COLORS["text_dark"], font=("Segoe UI", 10),
            padx=24, pady=18,
        ).pack()

        btns = tk.Frame(dlg, bg=COLORS["card_bg"])
        btns.pack(pady=(0, 18))
        ttk.Button(btns, text="Cancelar", style="Secondary.TButton", command=dlg.destroy).pack(side="left", padx=6)
        ttk.Button(
            btns, text="Ver archivos", style="Secondary.TButton", command=lambda: self._show_files_preview(candidates)
        ).pack(side="left", padx=6)

        def go_continue():
            dlg.destroy()
            self._show_step2_dialog(candidates, total_bytes)

        ttk.Button(btns, text="Continuar", style="Accent.TButton", command=go_continue).pack(side="left", padx=6)
        self._center_window(dlg)

    def _show_files_preview(self, candidates: List[XMLFileInfo]) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title(f"Archivos candidatos ({len(candidates):,})")
        dlg.configure(bg=COLORS["card_bg"])
        dlg.transient(self.root)
        dlg.geometry("640x420")

        frame = tk.Frame(dlg, bg=COLORS["card_bg"])
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        cols = ("name", "age", "size")
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        tree.heading("name", text="Nombre")
        tree.heading("age", text="Antigüedad")
        tree.heading("size", text="Tamaño")
        tree.column("name", width=340, anchor="w")
        tree.column("age", width=100, anchor="center")
        tree.column("size", width=100, anchor="e")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        for f in sorted(candidates, key=lambda x: x.age_days, reverse=True):
            tree.insert("", "end", values=(f.name, f.age_display, f.size_display))

        ttk.Button(dlg, text="Cerrar", style="Secondary.TButton", command=dlg.destroy).pack(pady=(0, 14))
        self._center_window(dlg)

    def _show_step2_dialog(self, candidates: List[XMLFileInfo], total_bytes: int) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Confirmar limpieza")
        dlg.configure(bg=COLORS["card_bg"])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        safe = self.safe_mode.get() or self.move_instead.get()
        archive_path = Path(self.current_folder) / self.settings.get("archive_folder", "XML_Archive")

        btns = tk.Frame(dlg, bg=COLORS["card_bg"])

        if safe:
            text = (
                f"Esta acción moverá {len(candidates):,} archivo(s) a la carpeta:\n{archive_path}\n\n"
                f"Espacio: {format_size(total_bytes)}\n\n"
                "SAFE MODE está activo: los archivos NO se eliminarán, solo se moverán.\n\n"
                "¿Confirmar?"
            )
            tk.Label(
                dlg, text=text, justify="center", bg=COLORS["card_bg"], fg=COLORS["text_dark"],
                font=("Segoe UI", 10), padx=24, pady=18, wraplength=420,
            ).pack()
            btns.pack(pady=(0, 18))
            ttk.Button(btns, text="Cancelar", style="Secondary.TButton", command=dlg.destroy).pack(side="left", padx=6)

            def confirm_move():
                dlg.destroy()
                self._execute_move(candidates)

            ttk.Button(btns, text="Confirmar", style="Accent.TButton", command=confirm_move).pack(side="left", padx=6)
        else:
            text = (
                "ADVERTENCIA: SAFE MODE está DESACTIVADO.\n\n"
                f"Esta acción ELIMINARÁ PERMANENTEMENTE {len(candidates):,} archivo(s)\n"
                f"({format_size(total_bytes)}).\n\n"
                "Esta acción NO se puede deshacer.\n\n"
                'Para confirmar, escribe ELIMINAR en el campo y presiona "Confirmar".'
            )
            tk.Label(
                dlg, text=text, justify="center", bg=COLORS["card_bg"], fg=COLORS["red"],
                font=("Segoe UI", 10, "bold"), padx=24, pady=18, wraplength=420,
            ).pack()

            confirm_var = tk.StringVar()
            entry = ttk.Entry(dlg, textvariable=confirm_var, width=20, justify="center")
            entry.pack(pady=(0, 14))

            btns.pack(pady=(0, 18))
            ttk.Button(btns, text="Cancelar", style="Secondary.TButton", command=dlg.destroy).pack(side="left", padx=6)
            confirm_btn = ttk.Button(btns, text="Confirmar", style="Danger.TButton", state="disabled")
            confirm_btn.pack(side="left", padx=6)

            def on_key(*_args):
                confirm_btn.config(state="normal" if confirm_var.get().strip() == "ELIMINAR" else "disabled")

            confirm_var.trace_add("write", on_key)

            def confirm_delete():
                dlg.destroy()
                self._execute_delete(candidates)

            confirm_btn.config(command=confirm_delete)

        self._center_window(dlg)

    def _make_progress_dialog(self, title: str) -> tk.Toplevel:
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg=COLORS["card_bg"])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)

        inner = tk.Frame(dlg, bg=COLORS["card_bg"])
        inner.pack(padx=24, pady=20)
        dlg.progress_label = tk.Label(inner, text="0 / 0", bg=COLORS["card_bg"], font=("Segoe UI", 10))
        dlg.progress_label.pack(pady=(0, 10))
        dlg.progress_bar = ttk.Progressbar(inner, orient="horizontal", length=320, mode="determinate")
        dlg.progress_bar.pack()

        def do_cancel():
            if self.cleanup_cancel_event is not None:
                self.cleanup_cancel_event.set()
            cancel_btn.config(state="disabled")

        cancel_btn = ttk.Button(inner, text="Cancelar", style="Secondary.TButton", command=do_cancel)
        cancel_btn.pack(pady=(12, 0))
        self._center_window(dlg)
        return dlg

    def _execute_move(self, candidates: List[XMLFileInfo]) -> None:
        self.cleanup_cancel_event = threading.Event()
        dlg = self._make_progress_dialog("Moviendo archivos a XML_Archive...")
        archive_folder = self.settings.get("archive_folder", "XML_Archive")
        folder = self.current_folder
        cancel_event = self.cleanup_cancel_event

        def progress_cb(done: int, total: int) -> None:
            self.move_queue.put(("progress", done, total))

        def worker():
            moved, errors = cleanup.move_files_safe(
                candidates, folder, archive_folder, dry_run=False, progress_callback=progress_cb, cancel_event=cancel_event
            )
            self.move_queue.put(("done", moved, errors))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_cleanup_queue(dlg, "movido(s) a XML_Archive")

    def _execute_delete(self, candidates: List[XMLFileInfo]) -> None:
        self.cleanup_cancel_event = threading.Event()
        dlg = self._make_progress_dialog("Eliminando archivos permanentemente...")
        cancel_event = self.cleanup_cancel_event

        def progress_cb(done: int, total: int) -> None:
            self.move_queue.put(("progress", done, total))

        def worker():
            deleted, errors = cleanup.delete_files_permanently(
                candidates, dry_run=False, progress_callback=progress_cb, cancel_event=cancel_event
            )
            self.move_queue.put(("done", deleted, errors))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_cleanup_queue(dlg, "eliminado(s) permanentemente")

    def _poll_cleanup_queue(self, dlg: tk.Toplevel, verb: str) -> None:
        try:
            while True:
                item = self.move_queue.get_nowait()
                if item[0] == "progress":
                    _, done, total = item
                    dlg.progress_bar["maximum"] = max(total, 1)
                    dlg.progress_bar["value"] = done
                    dlg.progress_label.config(text=f"{done:,} / {total:,}")
                elif item[0] == "done":
                    _, affected, errors = item
                    dlg.destroy()
                    msg = f"{len(affected):,} archivo(s) {verb}."
                    if errors:
                        msg += f"\n\n{len(errors)} error(es). Revisa el log para más detalles."
                    messagebox.showinfo("Operación completada", msg)
                    self.start_scan()
                    return
        except queue.Empty:
            pass
        self.root.after(80, lambda: self._poll_cleanup_queue(dlg, verb))

    # ------------------------------------------------------------------
    # Export report
    # ------------------------------------------------------------------
    def export_report(self) -> None:
        if not self.all_files:
            messagebox.showinfo("Sin datos", "Primero selecciona y analiza una carpeta.")
            return
        default_name = f"xml_diagnostic_{datetime.now().strftime('%Y-%m-%d')}.csv"
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile=default_name, filetypes=[("CSV", "*.csv")]
        )
        if not path:
            return
        try:
            export_set = self.filtered_files if self.filtered_files else self.all_files
            cleanup.export_csv(export_set, path)
            summary_path = str(Path(path).with_suffix("")) + "_summary.txt"
            cleanup.export_summary(self.all_files, self._get_current_retention_days(), summary_path)
            messagebox.showinfo("Exportación completa", f"Reporte exportado:\n{path}\n\nResumen:\n{summary_path}")
        except OSError as exc:
            logger.error("Export failed: %s", exc)
            messagebox.showerror("Error al exportar", str(exc))

    # ------------------------------------------------------------------
    # Settings dialog
    # ------------------------------------------------------------------
    def open_settings_dialog(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Configuración")
        dlg.configure(bg=COLORS["card_bg"])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        form = tk.Frame(dlg, bg=COLORS["card_bg"])
        form.pack(padx=24, pady=20)

        fields = [
            ("retention_days", "Retención por defecto (días)"),
            ("recent_days", "Verde (RECENT) — menos de (días)"),
            ("warning_days", "Amarillo (REVIEW) — desde (días)"),
            ("critical_days", "Naranja→Rojo (VERY OLD) — desde (días)"),
            ("archive_folder", "Carpeta de archivo (Safe Mode)"),
            ("api_port", "Puerto API local"),
        ]
        entry_vars = {}
        for i, (key, label) in enumerate(fields):
            tk.Label(form, text=label, bg=COLORS["card_bg"], fg=COLORS["text_dark"], font=("Segoe UI", 9)).grid(
                row=i, column=0, sticky="w", pady=5
            )
            var = tk.StringVar(value=str(self.settings.get(key, "")))
            ttk.Entry(form, textvariable=var, width=18).grid(row=i, column=1, padx=(16, 0), pady=5)
            entry_vars[key] = var

        def on_save():
            try:
                new_settings = dict(self.settings)
                new_settings["retention_days"] = int(entry_vars["retention_days"].get())
                new_settings["recent_days"] = int(entry_vars["recent_days"].get())
                new_settings["warning_days"] = int(entry_vars["warning_days"].get())
                new_settings["critical_days"] = int(entry_vars["critical_days"].get())
                new_settings["archive_folder"] = entry_vars["archive_folder"].get().strip() or "XML_Archive"
                new_port = int(entry_vars["api_port"].get())
            except ValueError:
                messagebox.showerror(
                    "Valor inválido", "Los campos numéricos deben ser enteros válidos.", parent=dlg
                )
                return
            if not (1 <= new_port <= 65535):
                messagebox.showerror("Puerto inválido", "El puerto debe estar entre 1 y 65535.", parent=dlg)
                return

            port_changed = new_port != self.settings.get("api_port")
            new_settings["api_port"] = new_port
            self.settings = new_settings
            config.save_settings(self.settings)

            self.retention_var.set(self._retention_label_for_days(self.settings["retention_days"]))
            self.custom_days_var.set(str(self.settings["retention_days"]))
            if self.retention_var.get() == "Personalizado":
                self.custom_days_spin.pack(side="left")
            else:
                self.custom_days_spin.pack_forget()

            self._reclassify_all_files()
            self._refresh_all_views()
            self.api_status_var.set(
                f"API: http://{self.settings.get('api_host', '127.0.0.1')}:{self.settings.get('api_port', 8765)}"
            )
            if port_changed:
                self._restart_api_server()
            dlg.destroy()
            messagebox.showinfo("Configuración guardada", "Los cambios se aplicaron correctamente.")

        btns = tk.Frame(dlg, bg=COLORS["card_bg"])
        btns.pack(pady=(0, 18))
        ttk.Button(btns, text="Cancelar", style="Secondary.TButton", command=dlg.destroy).pack(side="left", padx=6)
        ttk.Button(btns, text="Guardar", style="Accent.TButton", command=on_save).pack(side="left", padx=6)
        self._center_window(dlg)

    # ------------------------------------------------------------------
    # Local API server lifecycle
    # ------------------------------------------------------------------
    def _start_api(self) -> None:
        host = self.settings.get("api_host", "127.0.0.1")
        port = self.settings.get("api_port", 8765)
        try:
            api_config = uvicorn.Config(api_app, host=host, port=port, log_level="warning")
            self.api_server = uvicorn.Server(api_config)
            thread = threading.Thread(target=self.api_server.run, daemon=True, name="gpv-api-server")
            thread.start()
            logger.info("Local API server starting on http://%s:%d", host, port)
        except Exception as exc:  # noqa: BLE001 - API failures must never take down the GUI
            logger.error("Could not start local API server: %s", exc)

    def _restart_api_server(self) -> None:
        try:
            if self.api_server is not None:
                self.api_server.should_exit = True
        except Exception:  # noqa: BLE001
            pass
        self.root.after(500, self._start_api)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        try:
            if self.api_server is not None:
                self.api_server.should_exit = True
        except Exception:  # noqa: BLE001
            pass
        config.save_settings(self.settings)
        logger.info("Application closed by user")
        self.root.destroy()

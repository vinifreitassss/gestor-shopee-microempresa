import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from src.ui.theme import PAD


class SimpleTable(ctk.CTkFrame):
    def __init__(self, master, columns: list[tuple[str, str, int]], height: int = 12):
        super().__init__(master)
        self.columns = columns
        self.tree = ttk.Treeview(
            self,
            columns=[key for key, _, _ in columns],
            show="headings",
            height=height,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.scrollbar.set)

        for key, label, width in columns:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=80, anchor=tk.W)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def set_rows(self, rows: list[dict]) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            values = [row.get(key, "") for key, _, _ in self.columns]
            self.tree.insert("", "end", values=values)

    def selected_values(self) -> list[str] | None:
        selected = self.tree.selection()
        if not selected:
            return None
        return list(self.tree.item(selected[0], "values"))


class MetricCard(ctk.CTkFrame):
    def __init__(self, master, title: str, value: str = "-"):
        super().__init__(master)
        self.title_label = ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=13, weight="bold"))
        self.value_label = ctk.CTkLabel(self, text=value, font=ctk.CTkFont(size=20, weight="bold"))
        self.title_label.pack(anchor="w", padx=PAD, pady=(PAD, 2))
        self.value_label.pack(anchor="w", padx=PAD, pady=(0, PAD))

    def set_value(self, value: str) -> None:
        self.value_label.configure(text=value)

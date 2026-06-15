from tkinter import messagebox

import customtkinter as ctk

from src.services.launcher_service import (
    get_app,
    get_status_rows,
    open_app_folder,
    open_app_url,
    start_all,
    start_app,
    stop_all,
    stop_app,
)
from src.ui.components import SimpleTable
from src.ui.theme import PAD


class LauncherView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.status_var = ctk.StringVar(value="Central pronta para iniciar as automações.")
        self._build()

    def _build(self) -> None:
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            header,
            text="Central de Automações Shopee",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")

        actions = ctk.CTkFrame(self)
        actions.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(actions, text="Iniciar todos", command=self.start_all_apps).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(actions, text="Parar lançados", command=self.stop_all_apps).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(actions, text="Atualizar status", command=self.refresh).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(actions, textvariable=self.status_var, text_color="gray", wraplength=780, justify="left").pack(side="left", padx=16, pady=8)

        selected_actions = ctk.CTkFrame(self)
        selected_actions.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(selected_actions, text="Iniciar selecionado", command=self.start_selected).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(selected_actions, text="Abrir link selecionado", command=self.open_selected_url).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(selected_actions, text="Abrir pasta selecionada", command=self.open_selected_folder).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(selected_actions, text="Parar selecionado", command=self.stop_selected).pack(side="left", padx=8, pady=8)

        ctk.CTkLabel(
            self,
            text=(
                "Cada serviço será aberto em uma janela de CMD própria. "
                "O botão 'Parar' encerra apenas processos iniciados por esta central nesta sessão."
            ),
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        self.table = SimpleTable(
            self,
            [
                ("key", "ID", 110),
                ("nome", "App", 230),
                ("status", "Status", 170),
                ("porta", "Porta", 70),
                ("url", "Link", 170),
                ("comando", "Comando", 260),
                ("pasta", "Pasta", 420),
            ],
            height=10,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))

    def refresh(self) -> None:
        self.table.set_rows(get_status_rows())

    def start_all_apps(self) -> None:
        results = start_all()
        ok_count = sum(1 for _key, ok, _message in results if ok)
        self.status_var.set(f"{ok_count}/{len(results)} serviços iniciados ou já em execução.")
        self.refresh()

    def stop_all_apps(self) -> None:
        results = stop_all()
        stopped = sum(1 for _key, ok, _message in results if ok)
        self.status_var.set(f"{stopped} serviço(s) encerrado(s) pela central.")
        self.refresh()

    def start_selected(self) -> None:
        key = self._selected_key()
        if not key:
            return
        ok, message = start_app(key)
        self.status_var.set(message)
        if not ok:
            messagebox.showwarning("Não foi possível iniciar", message)
        self.refresh()

    def stop_selected(self) -> None:
        key = self._selected_key()
        if not key:
            return
        ok, message = stop_app(key)
        self.status_var.set(message)
        if not ok:
            messagebox.showinfo("Não encerrado", message)
        self.refresh()

    def open_selected_url(self) -> None:
        key = self._selected_key()
        if not key:
            return
        ok, message = open_app_url(key)
        self.status_var.set(message)
        if not ok:
            messagebox.showinfo("Sem link", message)

    def open_selected_folder(self) -> None:
        key = self._selected_key()
        if not key:
            return
        ok, message = open_app_folder(key)
        self.status_var.set(message)
        if not ok:
            messagebox.showwarning("Pasta não encontrada", message)

    def _selected_key(self) -> str | None:
        selected = self.table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione um app na tabela.")
            return None
        key = selected[0]
        if not get_app(key):
            messagebox.showwarning("Atenção", "App selecionado não encontrado.")
            return None
        return key

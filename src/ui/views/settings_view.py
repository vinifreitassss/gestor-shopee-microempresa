from tkinter import messagebox

import customtkinter as ctk

from src.services.settings_service import get_all_settings, set_setting
from src.ui.theme import PAD


class SettingsView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.imposto_var = ctk.StringVar(value="9")
        self.comissao_var = ctk.StringVar(value="22")
        self.taxa_var = ctk.StringVar(value="5")
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Configurações", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Esses valores valem para novas importações. Vendas já contabilizadas preservam o valor histórico.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=PAD)

        ctk.CTkLabel(form, text="Imposto padrão (%):").grid(row=0, column=0, padx=8, pady=10, sticky="w")
        ctk.CTkEntry(form, textvariable=self.imposto_var, width=120).grid(row=0, column=1, padx=8, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Comissão Shopee (%):").grid(row=1, column=0, padx=8, pady=10, sticky="w")
        ctk.CTkEntry(form, textvariable=self.comissao_var, width=120).grid(row=1, column=1, padx=8, pady=10, sticky="w")

        ctk.CTkLabel(form, text="Taxa fixa por unidade (R$):").grid(row=2, column=0, padx=8, pady=10, sticky="w")
        ctk.CTkEntry(form, textvariable=self.taxa_var, width=120).grid(row=2, column=1, padx=8, pady=10, sticky="w")

        ctk.CTkButton(form, text="Salvar configurações", command=self.save).grid(row=3, column=0, columnspan=2, padx=8, pady=16, sticky="w")

    def refresh(self) -> None:
        settings = get_all_settings()
        self.imposto_var.set(settings.get("imposto_percentual", "9"))
        self.comissao_var.set(settings.get("comissao_percentual", "22"))
        self.taxa_var.set(settings.get("taxa_fixa_unidade", "5"))

    def save(self) -> None:
        try:
            float(self.imposto_var.get().replace(",", "."))
            float(self.comissao_var.get().replace(",", "."))
            float(self.taxa_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Erro", "Informe apenas números nas configurações.")
            return
        set_setting("imposto_percentual", self.imposto_var.get().replace(",", "."))
        set_setting("comissao_percentual", self.comissao_var.get().replace(",", "."))
        set_setting("taxa_fixa_unidade", self.taxa_var.get().replace(",", "."))
        messagebox.showinfo("Configurações", "Configurações salvas com sucesso.")

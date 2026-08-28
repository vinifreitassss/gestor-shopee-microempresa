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
        self.ml_imposto_var = ctk.StringVar(value="9")
        self.ml_comissao_var = ctk.StringVar(value="22")
        self.ml_taxa_var = ctk.StringVar(value="8")
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Configurações", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Os valores valem para novas importações. Vendas já contabilizadas preservam os valores históricos.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=PAD)

        ctk.CTkLabel(form, text="SHOPEE", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, padx=8, pady=(12, 6), sticky="w")
        ctk.CTkLabel(form, text="Imposto (%):").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.imposto_var, width=120).grid(row=1, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(form, text="Comissão (%):").grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.comissao_var, width=120).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(form, text="Taxa fixa por unidade (R$):").grid(row=3, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.taxa_var, width=120).grid(row=3, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(form, text="MERCADO LIVRE", font=ctk.CTkFont(size=16, weight="bold")).grid(row=4, column=0, columnspan=2, padx=8, pady=(18, 6), sticky="w")
        ctk.CTkLabel(form, text="Imposto (%):").grid(row=5, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.ml_imposto_var, width=120).grid(row=5, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(form, text="Comissão (%):").grid(row=6, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.ml_comissao_var, width=120).grid(row=6, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(form, text="Taxa fixa por unidade (R$):").grid(row=7, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.ml_taxa_var, width=120).grid(row=7, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(
            form,
            text="As taxas do Mercado Livre são independentes das da Shopee. Ajuste-as conforme o seu contrato/anúncio no ML antes de usar o lucro como valor final.",
            text_color="gray",
            wraplength=700,
            justify="left",
        ).grid(row=8, column=0, columnspan=2, padx=8, pady=(4, 12), sticky="w")

        ctk.CTkButton(form, text="Salvar configurações", command=self.save).grid(row=9, column=0, columnspan=2, padx=8, pady=16, sticky="w")

    def refresh(self) -> None:
        settings = get_all_settings()
        self.imposto_var.set(settings.get("imposto_percentual", "9"))
        self.comissao_var.set(settings.get("comissao_percentual", "22"))
        self.taxa_var.set(settings.get("taxa_fixa_unidade", "5"))
        self.ml_imposto_var.set(settings.get("ml_imposto_percentual", "9"))
        self.ml_comissao_var.set(settings.get("ml_comissao_percentual", "22"))
        self.ml_taxa_var.set(settings.get("ml_taxa_fixa_unidade", "8"))

    def save(self) -> None:
        variables = (
            self.imposto_var,
            self.comissao_var,
            self.taxa_var,
            self.ml_imposto_var,
            self.ml_comissao_var,
            self.ml_taxa_var,
        )
        try:
            values = [float(var.get().replace(",", ".")) for var in variables]
            if any(value < 0 for value in values):
                raise ValueError
        except ValueError:
            messagebox.showerror("Erro", "Informe apenas números maiores ou iguais a zero nas configurações.")
            return

        keys = (
            "imposto_percentual",
            "comissao_percentual",
            "taxa_fixa_unidade",
            "ml_imposto_percentual",
            "ml_comissao_percentual",
            "ml_taxa_fixa_unidade",
        )
        for key, var in zip(keys, variables):
            set_setting(key, var.get().replace(",", "."))
        messagebox.showinfo("Configurações", "Configurações salvas com sucesso.")

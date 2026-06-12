from tkinter import messagebox

import customtkinter as ctk

from src.services.products_service import list_variations, save_variation_cost
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, money_to_float


class CostsView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.cost_var = ctk.StringVar(value="")
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Custos das Variações", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Na versão 1, o custo é manual. Depois entram insumos e ficha técnica para produtos fabricados.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(form, text="Selecione uma variação na tabela e informe o custo unitário:").pack(side="left", padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.cost_var, width=120, placeholder_text="Ex: 12,50").pack(side="left", padx=8, pady=8)
        ctk.CTkButton(form, text="Salvar custo", command=self.save_cost).pack(side="left", padx=8, pady=8)

        self.table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("produto_pai", "Produto pai", 360),
                ("nome_variacao", "Variação", 300),
                ("sku", "SKU", 120),
                ("custo_unitario", "Custo atual", 120),
            ],
            height=24,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)

    def save_cost(self) -> None:
        selected = self.table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma variação na tabela.")
            return
        try:
            variation_id = int(selected[0])
            cost = money_to_float(self.cost_var.get())
        except ValueError:
            messagebox.showerror("Erro", "Custo inválido.")
            return
        if cost <= 0:
            messagebox.showerror("Erro", "Informe um custo maior que zero.")
            return
        save_variation_cost(variation_id, cost)
        self.cost_var.set("")
        self.refresh()
        messagebox.showinfo("Custo salvo", "Custo atualizado com sucesso.")

    def refresh(self) -> None:
        rows = []
        for row in list_variations():
            rows.append(
                {
                    "id": row["id"],
                    "produto_pai": row["produto_pai"],
                    "nome_variacao": row["nome_variacao"],
                    "sku": row.get("sku") or "-",
                    "custo_unitario": brl(row["custo_unitario"]) if row["custo_unitario"] is not None else "Pendente",
                }
            )
        self.table.set_rows(rows)

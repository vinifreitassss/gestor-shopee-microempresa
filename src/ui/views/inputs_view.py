from tkinter import messagebox

import customtkinter as ctk

from src.services.inputs_service import add_input, deactivate_input, list_inputs, update_input_stock
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, money_to_float


class InputsView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.nome_var = ctk.StringVar(value="")
        self.unidade_var = ctk.StringVar(value="cm")
        self.quantidade_var = ctk.StringVar(value="")
        self.custo_var = ctk.StringVar(value="")
        self.uso_minimo_var = ctk.StringVar(value="")
        self.estoque_var = ctk.StringVar(value="")
        self.novo_estoque_var = ctk.StringVar(value="")
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Insumos / Estoque", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Cadastro pragmático: informe a quantidade total já na unidade de uso. Ex.: rolo de 50m de fita = 5000 cm.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=(0, PAD))

        ctk.CTkEntry(form, textvariable=self.nome_var, width=220, placeholder_text="Nome do insumo").grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.unidade_var, width=90, placeholder_text="Unid. uso").grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.quantidade_var, width=150, placeholder_text="Qtd total uso").grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.custo_var, width=130, placeholder_text="Custo compra").grid(row=0, column=3, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.uso_minimo_var, width=150, placeholder_text="Mínimo/pedido").grid(row=0, column=4, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.estoque_var, width=140, placeholder_text="Estoque atual").grid(row=0, column=5, padx=8, pady=8)
        ctk.CTkButton(form, text="Adicionar", command=self.add).grid(row=0, column=6, padx=8, pady=8)

        actions = ctk.CTkFrame(self)
        actions.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(actions, text="Selecione um insumo para atualizar estoque:").pack(side="left", padx=8, pady=8)
        ctk.CTkEntry(actions, textvariable=self.novo_estoque_var, width=140, placeholder_text="Novo estoque").pack(side="left", padx=8, pady=8)
        ctk.CTkButton(actions, text="Atualizar estoque", command=self.update_stock).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(actions, text="Desativar insumo", command=self.deactivate).pack(side="left", padx=8, pady=8)

        self.table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("nome", "Insumo", 220),
                ("unidade_uso", "Unid.", 70),
                ("quantidade_total_uso", "Qtd compra", 110),
                ("custo_compra", "Custo compra", 120),
                ("custo_por_unidade_uso", "Custo/unid.", 120),
                ("uso_minimo_por_pedido", "Mínimo/pedido", 120),
                ("custo_minimo_por_pedido", "Custo mínimo", 120),
                ("estoque_atual_uso", "Estoque", 100),
                ("valor_estoque", "Valor estoque", 120),
            ],
            height=22,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)

    def add(self) -> None:
        nome = self.nome_var.get().strip()
        unidade = self.unidade_var.get().strip()
        quantidade = money_to_float(self.quantidade_var.get())
        custo = money_to_float(self.custo_var.get())
        uso_minimo = money_to_float(self.uso_minimo_var.get())
        estoque = money_to_float(self.estoque_var.get())

        if not nome or not unidade or quantidade <= 0 or custo <= 0 or uso_minimo <= 0:
            messagebox.showwarning(
                "Atenção",
                "Preencha nome, unidade, quantidade total, custo da compra e mínimo usado por pedido.",
            )
            return

        add_input(nome, unidade, quantidade, custo, uso_minimo, estoque)
        self.nome_var.set("")
        self.quantidade_var.set("")
        self.custo_var.set("")
        self.uso_minimo_var.set("")
        self.estoque_var.set("")
        self.refresh()

    def update_stock(self) -> None:
        selected = self.table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione um insumo na tabela.")
            return
        estoque = money_to_float(self.novo_estoque_var.get())
        if estoque < 0:
            messagebox.showwarning("Atenção", "Informe um estoque válido.")
            return
        update_input_stock(int(selected[0]), estoque)
        self.novo_estoque_var.set("")
        self.refresh()

    def deactivate(self) -> None:
        selected = self.table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione um insumo na tabela.")
            return
        ok = messagebox.askyesno("Desativar", "Deseja desativar esse insumo?")
        if not ok:
            return
        deactivate_input(int(selected[0]))
        self.refresh()

    def refresh(self) -> None:
        rows = []
        for row in list_inputs():
            rows.append(
                {
                    "id": row["id"],
                    "nome": row["nome"],
                    "unidade_uso": row["unidade_uso"],
                    "quantidade_total_uso": f'{row["quantidade_total_uso"]:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."),
                    "custo_compra": brl(row["custo_compra"]),
                    "custo_por_unidade_uso": brl(row["custo_por_unidade_uso"]),
                    "uso_minimo_por_pedido": f'{row["uso_minimo_por_pedido"]:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."),
                    "custo_minimo_por_pedido": brl(row["custo_minimo_por_pedido"]),
                    "estoque_atual_uso": f'{row["estoque_atual_uso"]:,.2f}'.replace(",", "X").replace(".", ",").replace("X", "."),
                    "valor_estoque": brl(row["valor_estoque"]),
                }
            )
        self.table.set_rows(rows)

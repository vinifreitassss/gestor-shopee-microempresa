from tkinter import messagebox

import customtkinter as ctk

from src.services.inputs_service import (
    add_input,
    deactivate_input,
    get_input,
    list_inputs,
    update_input,
)
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, money_to_float


class InputsView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.selected_input_id: int | None = None
        self.nome_var = ctk.StringVar(value="")
        self.unidade_var = ctk.StringVar(value="cm")
        self.quantidade_var = ctk.StringVar(value="")
        self.custo_var = ctk.StringVar(value="")
        self.uso_minimo_var = ctk.StringVar(value="")
        self.estoque_var = ctk.StringVar(value="")
        self.status_var = ctk.StringVar(value="Modo: novo insumo")
        self.preview_var = ctk.StringVar(value="Preencha os dados para ver o cálculo.")
        self._build()
        self._bind_live_preview()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Insumos / Estoque", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Cadastre ou edite insumos. A quantidade total deve estar na unidade de uso. Ex.: rolo de 50m de fita = 5000 cm.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=(0, PAD))

        self._labeled_entry(form, "Nome do insumo", self.nome_var, 0, 0, 240, "Ex.: Fita amarela")
        self._labeled_entry(form, "Unidade de uso", self.unidade_var, 0, 1, 110, "cm")
        self._labeled_entry(form, "Qtd total na unidade de uso", self.quantidade_var, 0, 2, 180, "Ex.: 5000")
        self._labeled_entry(form, "Custo da compra", self.custo_var, 0, 3, 150, "Ex.: 8,27")
        self._labeled_entry(form, "Mínimo usado por pedido", self.uso_minimo_var, 0, 4, 180, "Ex.: 90")
        self._labeled_entry(form, "Estoque atual", self.estoque_var, 0, 5, 150, "Ex.: 5000")

        buttons = ctk.CTkFrame(self)
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Salvar novo", command=self.add).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(buttons, text="Atualizar selecionado", command=self.update_selected).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(buttons, text="Limpar / novo", command=self.clear_form).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(buttons, text="Desativar selecionado", command=self.deactivate).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(buttons, textvariable=self.status_var, text_color="gray").pack(side="left", padx=18, pady=8)

        preview = ctk.CTkFrame(self)
        preview.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(preview, text="Prévia do cálculo:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(preview, textvariable=self.preview_var).pack(side="left", padx=8, pady=8)

        ctk.CTkLabel(
            self,
            text="Clique em uma linha da tabela para carregar os dados no formulário acima e editar.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, 4))

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
            height=18,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)
        self.table.tree.bind("<<TreeviewSelect>>", self.load_selected)

    def _labeled_entry(self, master, label: str, variable: ctk.StringVar, row: int, column: int, width: int, placeholder: str):
        field = ctk.CTkFrame(master)
        field.grid(row=row, column=column, padx=8, pady=8, sticky="ew")
        ctk.CTkLabel(field, text=label, font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=4, pady=(2, 2))
        entry = ctk.CTkEntry(field, textvariable=variable, width=width, placeholder_text=placeholder)
        entry.pack(anchor="w", padx=4, pady=(0, 4))
        return entry

    def _bind_live_preview(self) -> None:
        for variable in [
            self.quantidade_var,
            self.custo_var,
            self.uso_minimo_var,
            self.estoque_var,
        ]:
            variable.trace_add("write", lambda *_: self.update_preview())

    def update_preview(self) -> None:
        quantidade = money_to_float(self.quantidade_var.get())
        custo = money_to_float(self.custo_var.get())
        uso_minimo = money_to_float(self.uso_minimo_var.get())
        estoque = money_to_float(self.estoque_var.get())

        if quantidade <= 0 or custo <= 0 or uso_minimo <= 0:
            self.preview_var.set("Preencha quantidade, custo e mínimo usado para calcular.")
            return

        custo_unidade = custo / quantidade
        custo_minimo = custo_unidade * uso_minimo
        valor_estoque = custo_unidade * estoque
        unidade = self.unidade_var.get().strip() or "un."
        self.preview_var.set(
            f"Custo por {unidade}: {brl(custo_unidade)} | "
            f"Custo mínimo/pedido: {brl(custo_minimo)} | "
            f"Valor em estoque: {brl(valor_estoque)}"
        )

    def _read_form(self) -> tuple[str, str, float, float, float, float] | None:
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
            return None
        return nome, unidade, quantidade, custo, uso_minimo, estoque

    def add(self) -> None:
        data = self._read_form()
        if data is None:
            return
        add_input(*data)
        self.clear_form()
        self.refresh()
        messagebox.showinfo("Insumo salvo", "Novo insumo cadastrado com sucesso.")

    def update_selected(self) -> None:
        if self.selected_input_id is None:
            messagebox.showwarning("Atenção", "Selecione um insumo na tabela para atualizar.")
            return
        data = self._read_form()
        if data is None:
            return
        update_input(self.selected_input_id, *data)
        self.refresh()
        messagebox.showinfo("Insumo atualizado", "Dados do insumo atualizados com sucesso.")

    def load_selected(self, _event=None) -> None:
        selected = self.table.selected_values()
        if not selected:
            return
        input_id = int(selected[0])
        item = get_input(input_id)
        if not item:
            return
        self.selected_input_id = input_id
        self.nome_var.set(str(item["nome"]))
        self.unidade_var.set(str(item["unidade_uso"]))
        self.quantidade_var.set(self._num(item["quantidade_total_uso"]))
        self.custo_var.set(self._num(item["custo_compra"]))
        self.uso_minimo_var.set(self._num(item["uso_minimo_por_pedido"]))
        self.estoque_var.set(self._num(item["estoque_atual_uso"]))
        self.status_var.set(f"Editando insumo ID {input_id}")
        self.update_preview()

    def clear_form(self) -> None:
        self.selected_input_id = None
        self.nome_var.set("")
        self.unidade_var.set("cm")
        self.quantidade_var.set("")
        self.custo_var.set("")
        self.uso_minimo_var.set("")
        self.estoque_var.set("")
        self.status_var.set("Modo: novo insumo")
        self.preview_var.set("Preencha os dados para ver o cálculo.")

    def deactivate(self) -> None:
        if self.selected_input_id is None:
            messagebox.showwarning("Atenção", "Selecione um insumo na tabela.")
            return
        ok = messagebox.askyesno("Desativar", "Deseja desativar esse insumo?")
        if not ok:
            return
        deactivate_input(self.selected_input_id)
        self.clear_form()
        self.refresh()

    def refresh(self) -> None:
        rows = []
        for row in list_inputs():
            rows.append(
                {
                    "id": row["id"],
                    "nome": row["nome"],
                    "unidade_uso": row["unidade_uso"],
                    "quantidade_total_uso": self._num(row["quantidade_total_uso"]),
                    "custo_compra": brl(row["custo_compra"]),
                    "custo_por_unidade_uso": brl(row["custo_por_unidade_uso"]),
                    "uso_minimo_por_pedido": self._num(row["uso_minimo_por_pedido"]),
                    "custo_minimo_por_pedido": brl(row["custo_minimo_por_pedido"]),
                    "estoque_atual_uso": self._num(row["estoque_atual_uso"]),
                    "valor_estoque": brl(row["valor_estoque"]),
                }
            )
        self.table.set_rows(rows)
        self.update_preview()

    def _num(self, value) -> str:
        return f"{float(value or 0):.4f}".rstrip("0").rstrip(".").replace(".", ",")

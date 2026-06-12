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
        self.unidade_var = ctk.StringVar(value="cm²")
        self.custo_ref_var = ctk.StringVar(value="")
        self.uso_ref_var = ctk.StringVar(value="")
        self.estoque_var = ctk.StringVar(value="")
        self.status_var = ctk.StringVar(value="Modo: nova matéria-prima")
        self.preview_var = ctk.StringVar(value="Preencha o custo ref. para ver o cálculo.")
        self._build()
        self._bind_live_preview()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Insumos / Estoque", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Cadastre o custo referência da matéria-prima. O produto usa esse custo ref. multiplicado pela quantidade usada.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=(0, PAD))

        self._labeled_entry(form, "Matéria-prima", self.nome_var, 0, 0, 250, "Ex.: Acrílico cristal 2mm")
        self._labeled_entry(form, "Unidade ref.", self.unidade_var, 0, 1, 120, "cm², cm, un.")
        self._labeled_entry(form, "Custo ref. por unidade", self.custo_ref_var, 0, 2, 170, "Ex.: 0,0068")
        self._labeled_entry(form, "Uso ref. opcional", self.uso_ref_var, 0, 3, 150, "Ex.: 25")
        self._labeled_entry(form, "Estoque atual na unid. ref.", self.estoque_var, 0, 4, 190, "Ex.: 21525")

        buttons = ctk.CTkFrame(self)
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Salvar novo", command=self.add).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(buttons, text="Atualizar selecionado", command=self.update_selected).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(buttons, text="Limpar / novo", command=self.clear_form).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(buttons, text="Desativar selecionado", command=self.deactivate).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(buttons, textvariable=self.status_var, text_color="gray").pack(side="left", padx=18, pady=8)

        preview = ctk.CTkFrame(self)
        preview.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(preview, text="Prévia:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(preview, textvariable=self.preview_var).pack(side="left", padx=8, pady=8)

        ctk.CTkLabel(
            self,
            text="Na aba Custos, o app fará: custo ref. × quantidade usada pela variação.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, 4))

        self.table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("nome", "Matéria-prima", 250),
                ("unidade_uso", "Unid. ref.", 90),
                ("custo_por_unidade_uso", "Custo ref.", 120),
                ("uso_minimo_por_pedido", "Uso ref.", 90),
                ("custo_minimo_por_pedido", "Custo uso ref.", 120),
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
        for variable in [self.custo_ref_var, self.uso_ref_var, self.estoque_var]:
            variable.trace_add("write", lambda *_: self.update_preview())

    def update_preview(self) -> None:
        custo_ref = money_to_float(self.custo_ref_var.get())
        uso_ref = money_to_float(self.uso_ref_var.get())
        estoque = money_to_float(self.estoque_var.get())
        unidade = self.unidade_var.get().strip() or "un."

        if custo_ref <= 0:
            self.preview_var.set("Informe o custo ref. por unidade. Ex.: R$ por cm², R$ por cm ou R$ por unidade.")
            return

        custo_uso_ref = custo_ref * uso_ref if uso_ref > 0 else 0
        valor_estoque = custo_ref * estoque
        if uso_ref > 0:
            self.preview_var.set(
                f"Custo ref.: {brl(custo_ref)} por {unidade} | "
                f"Uso ref.: {self._num(uso_ref)} {unidade} = {brl(custo_uso_ref)} | "
                f"Valor em estoque: {brl(valor_estoque)}"
            )
        else:
            self.preview_var.set(
                f"Custo ref.: {brl(custo_ref)} por {unidade} | "
                f"Valor em estoque: {brl(valor_estoque)}"
            )

    def _read_form(self) -> tuple[str, str, float, float, float, float] | None:
        nome = self.nome_var.get().strip()
        unidade = self.unidade_var.get().strip()
        custo_ref = money_to_float(self.custo_ref_var.get())
        uso_ref = money_to_float(self.uso_ref_var.get())
        estoque = money_to_float(self.estoque_var.get())

        if not nome or not unidade or custo_ref <= 0:
            messagebox.showwarning(
                "Atenção",
                "Preencha matéria-prima, unidade ref. e custo ref. por unidade.",
            )
            return None

        # Compatibilidade com banco legado:
        # quantidade_total_uso fica 1 e custo_compra passa a representar custo ref. direto.
        quantidade_total_uso = 1.0
        return nome, unidade, quantidade_total_uso, custo_ref, uso_ref, estoque

    def add(self) -> None:
        data = self._read_form()
        if data is None:
            return
        add_input(*data)
        self.clear_form()
        self.refresh()
        messagebox.showinfo("Matéria-prima salva", "Matéria-prima cadastrada com sucesso.")

    def update_selected(self) -> None:
        if self.selected_input_id is None:
            messagebox.showwarning("Atenção", "Selecione uma matéria-prima na tabela para atualizar.")
            return
        data = self._read_form()
        if data is None:
            return
        update_input(self.selected_input_id, *data)
        self.refresh()
        messagebox.showinfo("Matéria-prima atualizada", "Dados atualizados com sucesso.")

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
        self.custo_ref_var.set(self._num(item["custo_por_unidade_uso"]))
        self.uso_ref_var.set(self._num(item["uso_minimo_por_pedido"]))
        self.estoque_var.set(self._num(item["estoque_atual_uso"]))
        self.status_var.set(f"Editando matéria-prima ID {input_id}")
        self.update_preview()

    def clear_form(self) -> None:
        self.selected_input_id = None
        self.nome_var.set("")
        self.unidade_var.set("cm²")
        self.custo_ref_var.set("")
        self.uso_ref_var.set("")
        self.estoque_var.set("")
        self.status_var.set("Modo: nova matéria-prima")
        self.preview_var.set("Preencha o custo ref. para ver o cálculo.")

    def deactivate(self) -> None:
        if self.selected_input_id is None:
            messagebox.showwarning("Atenção", "Selecione uma matéria-prima na tabela.")
            return
        ok = messagebox.askyesno("Desativar", "Deseja desativar essa matéria-prima?")
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
        value = float(value or 0)
        if value == 0:
            return ""
        return f"{value:.6f}".rstrip("0").rstrip(".").replace(".", ",")

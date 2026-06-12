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
        self.valor_estoque_var = ctk.StringVar(value="")
        self.referencia_uso_var = ctk.StringVar(value="")
        self.status_var = ctk.StringVar(value="Modo: nova matéria-prima")
        self.preview_var = ctk.StringVar(value="Preencha o custo ref. para ver o cálculo.")
        self.audit_preview_var = ctk.StringVar(value="Auditoria de estoque: informe estoque e valor total gasto.")
        self._build()
        self._bind_live_preview()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Insumos / Estoque", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Separe custo de produção de auditoria: produto usa o custo ref.; estoque serve para conferir valor gasto e custo médio.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=(0, PAD))

        self._labeled_entry(form, "Matéria-prima", self.nome_var, 0, 0, 240, "Ex.: Acrílico cristal 2mm")
        self._labeled_entry(form, "Unidade ref.", self.unidade_var, 0, 1, 110, "cm², cm, un.")
        self._labeled_entry(form, "Custo ref. para produção", self.custo_ref_var, 0, 2, 180, "Ex.: 0,0068")
        self._labeled_entry(form, "Uso ref. opcional", self.uso_ref_var, 0, 3, 150, "Ex.: 25")

        self._labeled_entry(form, "Estoque atual", self.estoque_var, 1, 0, 140, "Ex.: 21525")
        self._labeled_entry(form, "Valor total gasto no estoque", self.valor_estoque_var, 1, 1, 190, "Ex.: 146,85")
        self._labeled_entry(form, "Referência de uso do custo", self.referencia_uso_var, 1, 2, 430, "Ex.: medalha adesiva 5 cm usa 25 cm²")

        buttons = ctk.CTkFrame(self)
        buttons.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkButton(buttons, text="Salvar novo", command=self.add).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(buttons, text="Atualizar selecionado", command=self.update_selected).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(buttons, text="Limpar / novo", command=self.clear_form).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(buttons, text="Desativar selecionado", command=self.deactivate).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(buttons, textvariable=self.status_var, text_color="gray").pack(side="left", padx=18, pady=8)

        preview = ctk.CTkFrame(self)
        preview.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(preview, text="Produção:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(preview, textvariable=self.preview_var).pack(side="left", padx=8, pady=8)

        audit = ctk.CTkFrame(self)
        audit.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(audit, text="Auditoria:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(audit, textvariable=self.audit_preview_var).pack(side="left", padx=8, pady=8)

        ctk.CTkLabel(
            self,
            text="Importante: custo médio do estoque é conferência. A ficha técnica usa o custo ref. para produção.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, 4))

        self.table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("nome", "Matéria-prima", 220),
                ("unidade_uso", "Unid. ref.", 80),
                ("custo_por_unidade_uso", "Custo ref.", 100),
                ("uso_minimo_por_pedido", "Uso ref.", 80),
                ("custo_minimo_por_pedido", "Custo uso ref.", 110),
                ("estoque_atual_uso", "Estoque", 90),
                ("valor_estoque", "Valor estoque", 115),
                ("custo_medio_estoque", "Médio estoque", 110),
                ("referencia_uso_custo", "Referência", 260),
            ],
            height=16,
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
            self.custo_ref_var,
            self.uso_ref_var,
            self.estoque_var,
            self.valor_estoque_var,
        ]:
            variable.trace_add("write", lambda *_: self.update_preview())

    def update_preview(self) -> None:
        custo_ref = money_to_float(self.custo_ref_var.get())
        uso_ref = money_to_float(self.uso_ref_var.get())
        estoque = money_to_float(self.estoque_var.get())
        valor_estoque = money_to_float(self.valor_estoque_var.get())
        unidade = self.unidade_var.get().strip() or "un."

        if custo_ref <= 0:
            self.preview_var.set("Informe o custo ref. que a ficha técnica usará. Ex.: R$ por cm², cm ou unidade.")
        elif uso_ref > 0:
            self.preview_var.set(
                f"Custo ref.: {brl(custo_ref)} por {unidade} | "
                f"Uso ref.: {self._num(uso_ref)} {unidade} = {brl(custo_ref * uso_ref)}"
            )
        else:
            self.preview_var.set(f"Custo ref.: {brl(custo_ref)} por {unidade}")

        if estoque > 0 and valor_estoque > 0:
            medio = valor_estoque / estoque
            self.audit_preview_var.set(
                f"Valor gasto no estoque: {brl(valor_estoque)} | "
                f"Estoque: {self._num(estoque)} {unidade} | "
                f"Médio de estoque: {brl(medio)} por {unidade}"
            )
        elif estoque > 0:
            self.audit_preview_var.set(f"Estoque cadastrado: {self._num(estoque)} {unidade}. Informe o valor total gasto para calcular o médio.")
        else:
            self.audit_preview_var.set("Auditoria de estoque: informe estoque e valor total gasto.")

    def _read_form(self) -> tuple[str, str, float, float, float, float, float, str] | None:
        nome = self.nome_var.get().strip()
        unidade = self.unidade_var.get().strip()
        custo_ref = money_to_float(self.custo_ref_var.get())
        uso_ref = money_to_float(self.uso_ref_var.get())
        estoque = money_to_float(self.estoque_var.get())
        valor_estoque = money_to_float(self.valor_estoque_var.get())
        referencia = self.referencia_uso_var.get().strip()

        if not nome or not unidade or custo_ref <= 0:
            messagebox.showwarning(
                "Atenção",
                "Preencha matéria-prima, unidade ref. e custo ref. para produção.",
            )
            return None

        quantidade_total_uso = 1.0
        return nome, unidade, quantidade_total_uso, custo_ref, uso_ref, estoque, valor_estoque, referencia

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
        self.valor_estoque_var.set(self._num(item.get("valor_total_estoque") or item.get("valor_estoque") or 0))
        self.referencia_uso_var.set(str(item.get("referencia_uso_custo") or ""))
        self.status_var.set(f"Editando matéria-prima ID {input_id}")
        self.update_preview()

    def clear_form(self) -> None:
        self.selected_input_id = None
        self.nome_var.set("")
        self.unidade_var.set("cm²")
        self.custo_ref_var.set("")
        self.uso_ref_var.set("")
        self.estoque_var.set("")
        self.valor_estoque_var.set("")
        self.referencia_uso_var.set("")
        self.status_var.set("Modo: nova matéria-prima")
        self.preview_var.set("Preencha o custo ref. para ver o cálculo.")
        self.audit_preview_var.set("Auditoria de estoque: informe estoque e valor total gasto.")

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
                    "custo_medio_estoque": brl(row["custo_medio_estoque"]),
                    "referencia_uso_custo": row.get("referencia_uso_custo") or "",
                }
            )
        self.table.set_rows(rows)
        self.update_preview()

    def _num(self, value) -> str:
        value = float(value or 0)
        if value == 0:
            return ""
        return f"{value:.6f}".rstrip("0").rstrip(".").replace(".", ",")

from tkinter import messagebox

import customtkinter as ctk

from src.services.inputs_service import get_input, list_inputs
from src.services.products_service import list_variations, save_variation_cost
from src.services.recipe_service import (
    add_or_update_recipe_item,
    apply_recipe_cost_to_variation,
    calculate_recipe_cost,
    list_recipe_items,
    remove_recipe_item,
)
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, money_to_float


class CostsView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.selected_variation_id: int | None = None
        self.selected_input_id: int | None = None
        self.selected_input_minimum: float = 0
        self.cost_var = ctk.StringVar(value="")
        self.quantidade_usada_var = ctk.StringVar(value="")
        self.status_var = ctk.StringVar(value="Selecione uma variação para montar a ficha técnica.")
        self.input_status_var = ctk.StringVar(value="Selecione um insumo e informe quanto dele essa variação usa.")
        self.recipe_total_var = ctk.StringVar(value="Custo calculado: R$ 0,00")
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Custos das Variações", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Produto pronto: use custo manual. Produto fabricado: monte a ficha técnica informando quanto de cada insumo é usado.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        manual_box = ctk.CTkFrame(self)
        manual_box.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(manual_box, text="Custo manual da variação selecionada:").pack(side="left", padx=8, pady=8)
        ctk.CTkEntry(manual_box, textvariable=self.cost_var, width=120, placeholder_text="Ex: 12,50").pack(side="left", padx=8, pady=8)
        ctk.CTkButton(manual_box, text="Salvar custo manual", command=self.save_manual_cost).pack(side="left", padx=8, pady=8)
        ctk.CTkLabel(manual_box, textvariable=self.status_var, text_color="gray").pack(side="left", padx=16, pady=8)

        content = ctk.CTkFrame(self)
        content.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        content.grid_columnconfigure(0, weight=2)
        content.grid_columnconfigure(1, weight=2)
        content.grid_columnconfigure(2, weight=2)
        content.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(content, text="1. Variações", font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        ctk.CTkLabel(content, text="2. Insumos cadastrados", font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=1, sticky="w", padx=6, pady=(6, 2))
        ctk.CTkLabel(content, text="3. Ficha técnica da variação", font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=2, sticky="w", padx=6, pady=(6, 2))

        self.variations_table = SimpleTable(
            content,
            [
                ("id", "ID", 50),
                ("produto_pai", "Produto", 220),
                ("nome_variacao", "Variação", 220),
                ("tipo_produto", "Tipo", 90),
                ("custo_unitario", "Custo", 100),
            ],
            height=16,
        )
        self.variations_table.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        self.variations_table.tree.bind("<<TreeviewSelect>>", self.load_variation)

        inputs_box = ctk.CTkFrame(content)
        inputs_box.grid(row=1, column=1, sticky="nsew", padx=6, pady=6)
        inputs_box.grid_rowconfigure(2, weight=1)
        inputs_box.grid_columnconfigure(0, weight=1)

        input_form = ctk.CTkFrame(inputs_box)
        input_form.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        ctk.CTkLabel(input_form, text="Qtd usada NESTA variação:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6, pady=6)
        ctk.CTkEntry(input_form, textvariable=self.quantidade_usada_var, width=110, placeholder_text="Ex.: 25").pack(side="left", padx=6, pady=6)
        ctk.CTkButton(input_form, text="Adicionar/atualizar", command=self.add_input_to_recipe).pack(side="left", padx=6, pady=6)
        ctk.CTkButton(input_form, text="Usar mínimo ref.", command=self.use_minimum_reference).pack(side="left", padx=6, pady=6)

        ctk.CTkLabel(
            inputs_box,
            textvariable=self.input_status_var,
            text_color="gray",
        ).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))

        self.inputs_table = SimpleTable(
            inputs_box,
            [
                ("id", "ID", 50),
                ("nome", "Insumo", 170),
                ("unidade_uso", "Unid.", 60),
                ("custo_por_unidade_uso", "Custo/unid.", 95),
                ("uso_minimo_por_pedido", "Mín. ref.", 80),
            ],
            height=12,
        )
        self.inputs_table.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        self.inputs_table.tree.bind("<<TreeviewSelect>>", self.load_input)

        recipe_box = ctk.CTkFrame(content)
        recipe_box.grid(row=1, column=2, sticky="nsew", padx=6, pady=6)
        recipe_box.grid_rowconfigure(1, weight=1)
        recipe_box.grid_columnconfigure(0, weight=1)

        recipe_actions = ctk.CTkFrame(recipe_box)
        recipe_actions.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        ctk.CTkLabel(recipe_actions, textvariable=self.recipe_total_var, font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6, pady=6)
        ctk.CTkButton(recipe_actions, text="Aplicar custo", command=self.apply_recipe_cost).pack(side="right", padx=6, pady=6)
        ctk.CTkButton(recipe_actions, text="Remover item", command=self.remove_recipe_item).pack(side="right", padx=6, pady=6)

        self.recipe_table = SimpleTable(
            recipe_box,
            [
                ("id", "ID", 50),
                ("insumo_nome", "Insumo", 160),
                ("quantidade_usada", "Qtd usada", 85),
                ("unidade_uso", "Unid.", 55),
                ("custo_por_unidade_uso", "Custo/unid.", 90),
                ("custo_item", "Custo item", 95),
            ],
            height=13,
        )
        self.recipe_table.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

    def save_manual_cost(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione uma variação na tabela.")
            return
        cost = money_to_float(self.cost_var.get())
        if cost <= 0:
            messagebox.showerror("Erro", "Informe um custo maior que zero.")
            return
        save_variation_cost(self.selected_variation_id, cost, origem_custo="manual")
        self.cost_var.set("")
        self.refresh()
        messagebox.showinfo("Custo salvo", "Custo manual atualizado com sucesso.")

    def load_variation(self, _event=None) -> None:
        selected = self.variations_table.selected_values()
        if not selected:
            return
        self.selected_variation_id = int(selected[0])
        self.status_var.set(f"Variação selecionada: ID {self.selected_variation_id}")
        self.refresh_recipe()

    def load_input(self, _event=None) -> None:
        selected = self.inputs_table.selected_values()
        if not selected:
            return
        self.selected_input_id = int(selected[0])
        item = get_input(self.selected_input_id)
        if not item:
            return
        self.selected_input_minimum = float(item["uso_minimo_por_pedido"] or 0)
        self.quantidade_usada_var.set("")
        self.input_status_var.set(
            f"Insumo selecionado: {item['nome']}. Custo por {item['unidade_uso']}: "
            f"{brl(item['custo_por_unidade_uso'])}. Informe o uso real desta variação. "
            f"Mínimo ref.: {self._num(item['uso_minimo_por_pedido'])} {item['unidade_uso']}."
        )

    def use_minimum_reference(self) -> None:
        if self.selected_input_id is None:
            messagebox.showwarning("Atenção", "Selecione um insumo primeiro.")
            return
        if self.selected_input_minimum <= 0:
            messagebox.showwarning("Atenção", "Esse insumo não tem mínimo de referência válido.")
            return
        self.quantidade_usada_var.set(self._num(self.selected_input_minimum))

    def add_input_to_recipe(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione uma variação primeiro.")
            return
        if self.selected_input_id is None:
            messagebox.showwarning("Atenção", "Selecione um insumo primeiro.")
            return
        quantidade = money_to_float(self.quantidade_usada_var.get())
        if quantidade <= 0:
            messagebox.showwarning("Atenção", "Informe quanto desse insumo é usado nessa variação. Ex.: se usa 25 peças de acrílico, informe 25.")
            return
        add_or_update_recipe_item(self.selected_variation_id, self.selected_input_id, quantidade)
        self.quantidade_usada_var.set("")
        self.refresh_recipe()

    def remove_recipe_item(self) -> None:
        selected = self.recipe_table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione um item da ficha técnica.")
            return
        remove_recipe_item(int(selected[0]))
        self.refresh_recipe()

    def apply_recipe_cost(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione uma variação primeiro.")
            return
        cost = apply_recipe_cost_to_variation(self.selected_variation_id)
        if cost <= 0:
            messagebox.showwarning("Atenção", "A ficha técnica ainda não tem custo calculado.")
            return
        self.refresh()
        self.refresh_recipe()
        messagebox.showinfo("Custo aplicado", f"Custo calculado aplicado na variação: {brl(cost)}")

    def refresh_recipe(self) -> None:
        if self.selected_variation_id is None:
            self.recipe_table.set_rows([])
            self.recipe_total_var.set("Custo calculado: R$ 0,00")
            return
        rows = []
        for row in list_recipe_items(self.selected_variation_id):
            rows.append(
                {
                    "id": row["id"],
                    "insumo_nome": row["insumo_nome"],
                    "quantidade_usada": self._num(row["quantidade_usada"]),
                    "unidade_uso": row["unidade_uso"],
                    "custo_por_unidade_uso": brl(row["custo_por_unidade_uso"]),
                    "custo_item": brl(row["custo_item"]),
                }
            )
        self.recipe_table.set_rows(rows)
        self.recipe_total_var.set(f"Custo calculado: {brl(calculate_recipe_cost(self.selected_variation_id))}")

    def refresh(self) -> None:
        variation_rows = []
        for row in list_variations():
            variation_rows.append(
                {
                    "id": row["id"],
                    "produto_pai": row["produto_pai"],
                    "nome_variacao": row["nome_variacao"],
                    "tipo_produto": row["tipo_produto"],
                    "custo_unitario": brl(row["custo_unitario"]) if row["custo_unitario"] is not None else "Pendente",
                }
            )
        self.variations_table.set_rows(variation_rows)

        input_rows = []
        for row in list_inputs():
            input_rows.append(
                {
                    "id": row["id"],
                    "nome": row["nome"],
                    "unidade_uso": row["unidade_uso"],
                    "custo_por_unidade_uso": brl(row["custo_por_unidade_uso"]),
                    "uso_minimo_por_pedido": self._num(row["uso_minimo_por_pedido"]),
                }
            )
        self.inputs_table.set_rows(input_rows)
        self.refresh_recipe()

    def _num(self, value) -> str:
        return f"{float(value or 0):.4f}".rstrip("0").rstrip(".").replace(".", ",")

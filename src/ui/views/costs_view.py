from tkinter import messagebox

import customtkinter as ctk

from src.services.inputs_service import list_inputs
from src.services.products_service import (
    apply_multiplier_rule,
    list_variations,
    remove_current_variation_cost,
    remove_multiplier_rule,
    save_variation_cost,
)
from src.services.recipe_service import (
    add_or_update_recipe_item,
    apply_recipe_cost_to_variation,
    calculate_recipe_cost,
    clear_recipe,
    list_recipe_items,
    remove_recipe_item,
)
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, money_to_float


EMPTY_VARIATION = "Selecione uma variação"
EMPTY_BASE_VARIATION = "Selecione a variação modelo"
EMPTY_MATERIAL = "Selecione uma matéria-prima"
EMPTY_RECIPE_ITEM = "Selecione um item da ficha"


class CostsView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.variations: list[dict] = []
        self.materials: list[dict] = []
        self.recipe_items: list[dict] = []
        self.variation_by_label: dict[str, dict] = {}
        self.base_variation_by_label: dict[str, dict] = {}
        self.material_by_label: dict[str, dict] = {}
        self.recipe_item_by_label: dict[str, dict] = {}
        self.selected_variation_id: int | None = None
        self.selected_material_id: int | None = None

        self.variation_var = ctk.StringVar(value=EMPTY_VARIATION)
        self.base_variation_var = ctk.StringVar(value=EMPTY_BASE_VARIATION)
        self.material_var = ctk.StringVar(value=EMPTY_MATERIAL)
        self.recipe_item_var = ctk.StringVar(value=EMPTY_RECIPE_ITEM)
        self.quantity_var = ctk.StringVar(value="")
        self.manual_cost_var = ctk.StringVar(value="")
        self.multiplier_var = ctk.StringVar(value="1")
        self.rule_description_var = ctk.StringVar(value="")
        self.variation_status_var = ctk.StringVar(value="Nenhuma variação selecionada.")
        self.rule_result_var = ctk.StringVar(value="Regra rápida: selecione uma base e informe o multiplicador.")
        self.material_status_var = ctk.StringVar(value="Escolha uma matéria-prima e informe quanto o produto usa.")
        self.item_preview_var = ctk.StringVar(value="Custo do item: R$ 0,00")
        self.recipe_total_var = ctk.StringVar(value="Custo atual da variação: R$ 0,00")

        self._build()
        self.quantity_var.trace_add("write", lambda *_: self.update_item_preview())

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Custos das Variações", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)
        ctk.CTkLabel(
            self,
            text="Você pode calcular por ficha técnica ou usar uma variação modelo com multiplicador. Ex.: 30 medalhas = custo da de 10 x 3.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        selector_box = ctk.CTkFrame(self)
        selector_box.pack(fill="x", padx=PAD, pady=(0, PAD))
        selector_box.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(selector_box, text="Variação:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        self.variation_menu = ctk.CTkOptionMenu(
            selector_box,
            variable=self.variation_var,
            values=[EMPTY_VARIATION],
            width=520,
            command=self.on_variation_selected,
        )
        self.variation_menu.grid(row=0, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkButton(selector_box, text="Atualizar listas", command=self.refresh).grid(row=0, column=2, padx=8, pady=8, sticky="e")
        ctk.CTkLabel(
            selector_box,
            textvariable=self.variation_status_var,
            text_color="gray",
            wraplength=900,
            justify="left",
        ).grid(row=1, column=1, columnspan=2, padx=8, pady=(0, 8), sticky="w")

        actions_box = ctk.CTkFrame(self)
        actions_box.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(actions_box, text="Custo manual:").pack(side="left", padx=8, pady=8)
        ctk.CTkEntry(actions_box, textvariable=self.manual_cost_var, width=120, placeholder_text="Ex.: 12,50").pack(side="left", padx=8, pady=8)
        ctk.CTkButton(actions_box, text="Salvar custo manual", command=self.save_manual_cost).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(actions_box, text="Remover custo atual", command=self.remove_active_cost).pack(side="left", padx=8, pady=8)

        rule_box = ctk.CTkFrame(self)
        rule_box.pack(fill="x", padx=PAD, pady=(0, PAD))
        rule_box.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(rule_box, text="Regra rápida / produtos semelhantes", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=4, padx=8, pady=(8, 2), sticky="w")

        ctk.CTkLabel(rule_box, text="Base:").grid(row=1, column=0, padx=8, pady=6, sticky="w")
        self.base_variation_menu = ctk.CTkOptionMenu(
            rule_box,
            variable=self.base_variation_var,
            values=[EMPTY_BASE_VARIATION],
            width=520,
        )
        self.base_variation_menu.grid(row=1, column=1, padx=8, pady=6, sticky="w")
        ctk.CTkLabel(rule_box, text="Multiplicador:").grid(row=1, column=2, padx=8, pady=6, sticky="w")
        ctk.CTkEntry(rule_box, textvariable=self.multiplier_var, width=90, placeholder_text="1,2").grid(row=1, column=3, padx=8, pady=6, sticky="w")

        ctk.CTkLabel(rule_box, text="Obs.:").grid(row=2, column=0, padx=8, pady=6, sticky="w")
        ctk.CTkEntry(rule_box, textvariable=self.rule_description_var, width=520, placeholder_text="Ex.: 30 medalhas = 3x / semelhante = 1x").grid(row=2, column=1, padx=8, pady=6, sticky="w")
        ctk.CTkButton(rule_box, text="Aplicar regra", command=self.apply_multiplier_cost_rule).grid(row=2, column=2, padx=8, pady=6, sticky="w")
        ctk.CTkButton(rule_box, text="Remover regra", command=self.remove_selected_multiplier_rule).grid(row=2, column=3, padx=8, pady=6, sticky="w")
        ctk.CTkLabel(rule_box, textvariable=self.rule_result_var, text_color="gray", wraplength=900, justify="left").grid(row=3, column=1, columnspan=3, padx=8, pady=(0, 8), sticky="w")

        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=PAD, pady=(0, PAD))
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        self.material_box = ctk.CTkFrame(main)
        self.material_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)
        self.material_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.material_box, text="Ficha técnica manual", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4))
        ctk.CTkLabel(self.material_box, text="Matéria-prima:").grid(row=1, column=0, sticky="w", padx=8, pady=(8, 2))
        self.material_menu = ctk.CTkOptionMenu(
            self.material_box,
            variable=self.material_var,
            values=[EMPTY_MATERIAL],
            width=440,
            command=self.on_material_selected,
        )
        self.material_menu.grid(row=2, column=0, sticky="w", padx=8, pady=(0, 8))

        ctk.CTkLabel(self.material_box, textvariable=self.material_status_var, text_color="gray", wraplength=520, justify="left").grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))

        quantity_row = ctk.CTkFrame(self.material_box)
        quantity_row.grid(row=4, column=0, sticky="ew", padx=8, pady=8)
        ctk.CTkLabel(quantity_row, text="Quanto esta variação usa:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=6, pady=6)
        ctk.CTkEntry(quantity_row, textvariable=self.quantity_var, width=120, placeholder_text="Ex.: 25").pack(side="left", padx=6, pady=6)
        ctk.CTkButton(quantity_row, text="Adicionar / atualizar", command=self.add_material_to_recipe).pack(side="left", padx=6, pady=6)

        ctk.CTkLabel(self.material_box, textvariable=self.item_preview_var, font=ctk.CTkFont(weight="bold")).grid(row=5, column=0, sticky="w", padx=8, pady=(0, 8))

        examples = (
            "Exemplos:\n"
            "• Base 10 medalhas: monte a ficha uma vez. 30 medalhas pode ser regra x3.\n"
            "• Produtos semelhantes: escolha a base e use x1, x1,2 etc."
        )
        ctk.CTkLabel(self.material_box, text=examples, text_color="gray", justify="left").grid(row=6, column=0, sticky="w", padx=8, pady=(8, 8))

        self.recipe_box = ctk.CTkFrame(main)
        self.recipe_box.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)
        self.recipe_box.grid_columnconfigure(0, weight=1)
        self.recipe_box.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(self.recipe_box, text="Resumo do custo da variação", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ctk.CTkLabel(self.recipe_box, textvariable=self.recipe_total_var, font=ctk.CTkFont(size=15, weight="bold"), wraplength=520, justify="left").grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))

        recipe_actions = ctk.CTkFrame(self.recipe_box)
        recipe_actions.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.recipe_item_menu = ctk.CTkOptionMenu(
            recipe_actions,
            variable=self.recipe_item_var,
            values=[EMPTY_RECIPE_ITEM],
            width=360,
        )
        self.recipe_item_menu.pack(side="left", padx=6, pady=6)
        ctk.CTkButton(recipe_actions, text="Remover item", command=self.remove_selected_recipe_item).pack(side="left", padx=6, pady=6)
        ctk.CTkButton(recipe_actions, text="Limpar ficha", command=self.clear_current_recipe).pack(side="left", padx=6, pady=6)

        self.recipe_table = SimpleTable(
            self.recipe_box,
            [
                ("insumo_nome", "Matéria-prima", 180),
                ("quantidade_usada", "Qtd usada", 95),
                ("unidade_uso", "Unid.", 60),
                ("custo_por_unidade_uso", "Custo base", 100),
                ("custo_item", "Custo item", 100),
            ],
            height=12,
        )
        self.recipe_table.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 8))

        bottom_actions = ctk.CTkFrame(self.recipe_box)
        bottom_actions.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
        ctk.CTkButton(bottom_actions, text="Aplicar custo calculado na variação", command=self.apply_recipe_cost).pack(side="left", padx=6, pady=6)

    def refresh(self) -> None:
        old_variation_id = self.selected_variation_id
        old_material_id = self.selected_material_id
        old_base_id = self._id_from_label(self.base_variation_by_label, self.base_variation_var.get())

        self.variations = list_variations()
        self.materials = list_inputs()

        self.variation_by_label = {}
        self.base_variation_by_label = {}
        variation_labels = []
        for row in self.variations:
            label = self._variation_label(row)
            self.variation_by_label[label] = row
            self.base_variation_by_label[label] = row
            variation_labels.append(label)
        self.variation_menu.configure(values=variation_labels or [EMPTY_VARIATION])
        self.base_variation_menu.configure(values=variation_labels or [EMPTY_BASE_VARIATION])

        selected_label = self._label_for_id(self.variation_by_label, old_variation_id)
        if selected_label:
            self.variation_var.set(selected_label)
            self.selected_variation_id = old_variation_id
            current_row = self.variation_by_label[selected_label]
            self.update_variation_status(current_row)
            self.load_rule_fields(current_row, fallback_base_id=old_base_id)
        else:
            self.variation_var.set(EMPTY_VARIATION)
            self.selected_variation_id = None
            self.variation_status_var.set("Nenhuma variação selecionada.")
            self.base_variation_var.set(EMPTY_BASE_VARIATION)

        self.material_by_label = {}
        material_labels = []
        for row in self.materials:
            label = self._material_label(row)
            self.material_by_label[label] = row
            material_labels.append(label)
        self.material_menu.configure(values=material_labels or [EMPTY_MATERIAL])

        material_label = self._label_for_id(self.material_by_label, old_material_id)
        if material_label:
            self.material_var.set(material_label)
            self.selected_material_id = old_material_id
            self.update_material_status(self.material_by_label[material_label])
        else:
            self.material_var.set(EMPTY_MATERIAL)
            self.selected_material_id = None
            self.material_status_var.set("Escolha uma matéria-prima e informe quanto o produto usa.")
            self.item_preview_var.set("Custo do item: R$ 0,00")

        self.refresh_recipe()

    def on_variation_selected(self, label: str) -> None:
        row = self.variation_by_label.get(label)
        if not row:
            self.selected_variation_id = None
            self.variation_status_var.set("Nenhuma variação selecionada.")
            self.base_variation_var.set(EMPTY_BASE_VARIATION)
            self.refresh_recipe()
            return
        self.selected_variation_id = int(row["id"])
        self.update_variation_status(row)
        self.load_rule_fields(row)
        self.refresh_recipe()

    def update_variation_status(self, row: dict) -> None:
        cost = brl(row["custo_unitario"]) if row.get("custo_unitario") is not None else "Pendente"
        origem = row.get("origem_custo") or "sem origem"
        rule = ""
        if row.get("base_variacao_id"):
            base_name = f"{row.get('base_produto_pai') or ''} / {row.get('base_nome_variacao') or ''}"
            rule = f" | Regra: {self._clip(base_name, 70)} x {self._num(row.get('regra_multiplicador') or 1)}"
        self.variation_status_var.set(
            f"Selecionada: {self._clip(row['produto_pai'], 60)} / {self._clip(row['nome_variacao'], 45)} | Custo atual: {cost} | Origem: {origem}{rule}"
        )

    def load_rule_fields(self, row: dict, fallback_base_id: int | None = None) -> None:
        base_id = int(row["base_variacao_id"]) if row.get("base_variacao_id") else fallback_base_id
        base_label = self._label_for_id(self.base_variation_by_label, base_id)
        self.base_variation_var.set(base_label or EMPTY_BASE_VARIATION)
        if row.get("regra_multiplicador"):
            self.multiplier_var.set(self._num(row.get("regra_multiplicador") or 1))
            self.rule_description_var.set(row.get("regra_descricao") or "")
        elif not self.multiplier_var.get().strip():
            self.multiplier_var.set("1")

    def apply_multiplier_cost_rule(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione a variação que receberá o custo.")
            return
        base = self.base_variation_by_label.get(self.base_variation_var.get())
        if not base:
            messagebox.showwarning("Atenção", "Selecione a variação modelo.")
            return
        multiplier = money_to_float(self.multiplier_var.get())
        if multiplier <= 0:
            messagebox.showwarning("Atenção", "Informe um multiplicador maior que zero. Ex.: 1, 1,2 ou 3.")
            return
        try:
            cost = apply_multiplier_rule(
                variacao_id=self.selected_variation_id,
                base_variacao_id=int(base["id"]),
                multiplicador=multiplier,
                descricao=self.rule_description_var.get().strip(),
            )
        except ValueError as exc:
            messagebox.showerror("Erro na regra", str(exc))
            return
        self.rule_result_var.set(
            f"Regra aplicada: custo atual = {brl(cost)} ({self._clip(base['produto_pai'], 35)} / {self._clip(base['nome_variacao'], 30)} × {self._num(multiplier)})."
        )
        self.refresh()
        messagebox.showinfo("Regra aplicada", f"Custo aplicado pela regra: {brl(cost)}")

    def remove_selected_multiplier_rule(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione uma variação primeiro.")
            return
        removed = remove_multiplier_rule(self.selected_variation_id)
        if not removed:
            messagebox.showinfo("Sem regra", "Essa variação não possui regra multiplicadora ativa.")
            return
        self.rule_result_var.set("Regra removida. O custo atual não foi apagado.")
        self.refresh()
        messagebox.showinfo("Regra removida", "A regra multiplicadora foi removida. O custo atual não foi apagado.")

    def on_material_selected(self, label: str) -> None:
        row = self.material_by_label.get(label)
        if not row:
            self.selected_material_id = None
            self.material_status_var.set("Escolha uma matéria-prima e informe quanto o produto usa.")
            self.item_preview_var.set("Custo do item: R$ 0,00")
            return
        self.selected_material_id = int(row["id"])
        self.quantity_var.set("")
        self.update_material_status(row)
        self.update_item_preview()

    def update_material_status(self, row: dict) -> None:
        unidade = row["unidade_uso"]
        self.material_status_var.set(
            f"{row['nome']} | custo ref.: {brl(row['custo_por_unidade_uso'])} por {unidade}. "
            f"Informe a quantidade usada nesta variação nessa mesma unidade."
        )

    def update_item_preview(self) -> None:
        material = self.get_selected_material()
        quantity = money_to_float(self.quantity_var.get())
        if not material or quantity <= 0:
            self.item_preview_var.set("Custo do item: R$ 0,00")
            return
        cost = float(material["custo_por_unidade_uso"] or 0) * quantity
        self.item_preview_var.set(
            f"Custo do item: {brl(cost)}  ({self._num(quantity)} {material['unidade_uso']} × {brl(material['custo_por_unidade_uso'])})"
        )

    def add_material_to_recipe(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione uma variação primeiro.")
            return
        if self.selected_material_id is None:
            messagebox.showwarning("Atenção", "Selecione uma matéria-prima primeiro.")
            return
        quantity = money_to_float(self.quantity_var.get())
        if quantity <= 0:
            messagebox.showwarning("Atenção", "Informe quanto dessa matéria-prima a variação usa.")
            return
        add_or_update_recipe_item(self.selected_variation_id, self.selected_material_id, quantity)
        self.quantity_var.set("")
        self.refresh_recipe()

    def save_manual_cost(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione uma variação primeiro.")
            return
        cost = money_to_float(self.manual_cost_var.get())
        if cost <= 0:
            messagebox.showwarning("Atenção", "Informe um custo manual maior que zero.")
            return
        save_variation_cost(self.selected_variation_id, cost, origem_custo="manual")
        self.manual_cost_var.set("")
        self.rule_result_var.set("Custo manual aplicado. Se havia regra multiplicadora nessa variação, ela foi removida.")
        self.refresh()
        messagebox.showinfo("Custo salvo", "Custo manual salvo na variação.")

    def remove_active_cost(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione uma variação primeiro.")
            return
        ok = messagebox.askyesno(
            "Remover custo atual",
            "Remover o custo atual desta variação?\n\n"
            "As vendas ainda não fechadas voltarão para lucro incompleto até um novo custo ser aplicado.",
        )
        if not ok:
            return
        removed = remove_current_variation_cost(self.selected_variation_id)
        if not removed:
            messagebox.showinfo("Sem custo", "Essa variação não possui custo ativo para remover.")
            return
        self.rule_result_var.set("Custo atual removido. A regra ativa, se existia, também foi removida.")
        self.refresh()
        messagebox.showinfo("Custo removido", "Custo atual removido da variação.")

    def refresh_recipe(self) -> None:
        selected_row = self.get_selected_variation_row()
        if self.selected_variation_id is None:
            self.recipe_items = []
            self.recipe_table.set_rows([])
            self.recipe_total_var.set("Custo atual da variação: R$ 0,00")
            self.recipe_item_by_label = {}
            self.recipe_item_menu.configure(values=[EMPTY_RECIPE_ITEM])
            self.recipe_item_var.set(EMPTY_RECIPE_ITEM)
            return

        self.recipe_items = list_recipe_items(self.selected_variation_id)
        rows = []
        self.recipe_item_by_label = {}
        recipe_labels = []
        for item in self.recipe_items:
            label = self._recipe_item_label(item)
            recipe_labels.append(label)
            self.recipe_item_by_label[label] = item
            rows.append(
                {
                    "insumo_nome": item["insumo_nome"],
                    "quantidade_usada": self._num(item["quantidade_usada"]),
                    "unidade_uso": item["unidade_uso"],
                    "custo_por_unidade_uso": brl(item["custo_por_unidade_uso"]),
                    "custo_item": brl(item["custo_item"]),
                }
            )
        self.recipe_table.set_rows(rows)
        self.recipe_item_menu.configure(values=recipe_labels or [EMPTY_RECIPE_ITEM])
        self.recipe_item_var.set(recipe_labels[0] if recipe_labels else EMPTY_RECIPE_ITEM)

        recipe_cost = calculate_recipe_cost(self.selected_variation_id)
        if self.recipe_items:
            self.recipe_total_var.set(f"Custo da ficha manual: {brl(recipe_cost)}")
        elif selected_row and selected_row.get("custo_unitario") is not None:
            origem = selected_row.get("origem_custo") or "sem origem"
            self.recipe_total_var.set(f"Custo atual da variação: {brl(selected_row['custo_unitario'])} | Origem: {origem} | Ficha manual vazia")
        else:
            self.recipe_total_var.set("Custo atual da variação: Pendente | Ficha manual vazia")

    def remove_selected_recipe_item(self) -> None:
        label = self.recipe_item_var.get()
        item = self.recipe_item_by_label.get(label)
        if not item:
            messagebox.showwarning("Atenção", "Selecione um item da ficha para remover.")
            return
        remove_recipe_item(int(item["id"]))
        self.refresh_recipe()

    def clear_current_recipe(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione uma variação primeiro.")
            return
        if not self.recipe_items:
            messagebox.showinfo("Ficha vazia", "Essa variação ainda não tem itens na ficha técnica.")
            return
        ok = messagebox.askyesno("Limpar ficha técnica", "Remover todos os itens da ficha técnica desta variação?")
        if not ok:
            return
        clear_recipe(self.selected_variation_id)
        self.refresh_recipe()

    def apply_recipe_cost(self) -> None:
        if self.selected_variation_id is None:
            messagebox.showwarning("Atenção", "Selecione uma variação primeiro.")
            return
        if not self.recipe_items:
            messagebox.showwarning("Atenção", "Adicione ao menos uma matéria-prima na ficha técnica.")
            return
        cost = apply_recipe_cost_to_variation(self.selected_variation_id)
        if cost <= 0:
            messagebox.showwarning("Atenção", "A ficha técnica ainda não tem custo calculado.")
            return
        self.rule_result_var.set("Custo aplicado pela ficha técnica manual.")
        self.refresh()
        messagebox.showinfo("Custo aplicado", f"Custo calculado aplicado na variação: {brl(cost)}")

    def get_selected_material(self) -> dict | None:
        if self.selected_material_id is None:
            return None
        for material in self.materials:
            if int(material["id"]) == self.selected_material_id:
                return material
        return None

    def get_selected_variation_row(self) -> dict | None:
        if self.selected_variation_id is None:
            return None
        for row in self.variations:
            if int(row["id"]) == self.selected_variation_id:
                return row
        return None

    def _variation_label(self, row: dict) -> str:
        cost = brl(row["custo_unitario"]) if row.get("custo_unitario") is not None else "Pendente"
        product = self._clip(row["produto_pai"], 34)
        variation = self._clip(row["nome_variacao"], 30)
        return f"{row['id']} | {product} / {variation} | {cost}"

    def _material_label(self, row: dict) -> str:
        return f"{row['id']} | {self._clip(row['nome'], 38)} | {brl(row['custo_por_unidade_uso'])}/{row['unidade_uso']}"

    def _recipe_item_label(self, item: dict) -> str:
        return f"{item['id']} | {self._clip(item['insumo_nome'], 32)} | {self._num(item['quantidade_usada'])} {item['unidade_uso']} | {brl(item['custo_item'])}"

    def _label_for_id(self, mapping: dict[str, dict], item_id: int | None) -> str | None:
        if item_id is None:
            return None
        for label, row in mapping.items():
            if int(row["id"]) == int(item_id):
                return label
        return None

    def _id_from_label(self, mapping: dict[str, dict], label: str) -> int | None:
        row = mapping.get(label)
        if not row:
            return None
        return int(row["id"])

    def _clip(self, text, limit: int) -> str:
        value = str(text or "")
        if len(value) <= limit:
            return value
        return value[: limit - 3] + "..."

    def _num(self, value) -> str:
        value = float(value or 0)
        if value == 0:
            return "0"
        return f"{value:.4f}".rstrip("0").rstrip(".").replace(".", ",")

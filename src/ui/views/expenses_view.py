from datetime import date
from tkinter import messagebox

import customtkinter as ctk

from src.services.expenses_service import (
    DRE_IMPACT_OPTIONS,
    EXPENSE_CATEGORIES,
    add_expense,
    add_recurring_expense,
    deactivate_recurring_expense,
    delete_expense,
    generate_recurring_for_month,
    list_expenses,
    list_recurring_expenses,
)
from src.services.reports_service import current_month_reference
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, money_to_float


CASH_ONLY_CATEGORIES = {"Investimento em estoque", "Compra de insumos", "Retirada / pró-labore"}


class ExpensesView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.month_var = ctk.StringVar(value=current_month_reference())
        self.date_var = ctk.StringVar(value=date.today().isoformat())
        self.category_var = ctk.StringVar(value="Investimento em estoque")
        self.impact_var = ctk.StringVar(value="Somente fluxo de caixa")
        self.description_var = ctk.StringVar(value="")
        self.value_var = ctk.StringVar(value="")
        self.rec_category_var = ctk.StringVar(value="Operacional")
        self.rec_impact_var = ctk.StringVar(value="Entra no DRE")
        self.rec_description_var = ctk.StringVar(value="")
        self.rec_value_var = ctk.StringVar(value="")
        self.rec_day_var = ctk.StringVar(value="1")
        self._build()
        self.refresh()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Despesas / Saídas de caixa", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=(0, PAD))

        ctk.CTkLabel(form, text="Data:").grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.date_var, width=115).grid(row=0, column=1, padx=8, pady=8)

        ctk.CTkLabel(form, text="Categoria:").grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkOptionMenu(form, variable=self.category_var, values=EXPENSE_CATEGORIES, command=self._on_category_selected, width=180).grid(row=0, column=3, padx=8, pady=8)

        ctk.CTkLabel(form, text="Impacto:").grid(row=0, column=4, padx=8, pady=8)
        ctk.CTkOptionMenu(form, variable=self.impact_var, values=list(DRE_IMPACT_OPTIONS.keys()), width=170).grid(row=0, column=5, padx=8, pady=8)

        ctk.CTkLabel(form, text="Valor:").grid(row=0, column=6, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.value_var, width=100).grid(row=0, column=7, padx=8, pady=8)

        ctk.CTkLabel(form, text="Descrição:").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.description_var, width=520).grid(row=1, column=1, columnspan=5, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(form, text="Adicionar saída", command=self.add).grid(row=1, column=6, columnspan=2, padx=8, pady=8, sticky="ew")
        form.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(
            self,
            text="Use 'Somente fluxo de caixa' para compra de estoque/insumos: reduz o caixa, mas não entra no DRE.",
            text_color="gray",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        controls = ctk.CTkFrame(self)
        controls.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(controls, text="Mês:").pack(side="left", padx=8, pady=8)
        ctk.CTkEntry(controls, textvariable=self.month_var, width=90).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(controls, text="Atualizar", command=self.refresh).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(controls, text="Excluir saída selecionada", command=self.delete_selected_expense).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(controls, text="Gerar recorrentes do mês", command=self.generate_recurring).pack(side="left", padx=8, pady=8)

        self.table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("data", "Data", 110),
                ("categoria", "Categoria", 170),
                ("impacto", "Impacto", 160),
                ("descricao", "Descrição", 330),
                ("valor", "Valor", 120),
            ],
            height=14,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        ctk.CTkLabel(self, text="Saídas recorrentes", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        rec_form = ctk.CTkFrame(self)
        rec_form.pack(fill="x", padx=PAD, pady=(6, PAD))
        ctk.CTkOptionMenu(rec_form, variable=self.rec_category_var, values=EXPENSE_CATEGORIES, command=self._on_rec_category_selected, width=160).grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkOptionMenu(rec_form, variable=self.rec_impact_var, values=list(DRE_IMPACT_OPTIONS.keys()), width=160).grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkEntry(rec_form, textvariable=self.rec_description_var, width=250, placeholder_text="Descrição").grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkEntry(rec_form, textvariable=self.rec_value_var, width=110, placeholder_text="Valor").grid(row=0, column=3, padx=8, pady=8)
        ctk.CTkEntry(rec_form, textvariable=self.rec_day_var, width=80, placeholder_text="Dia").grid(row=0, column=4, padx=8, pady=8)
        ctk.CTkButton(rec_form, text="Cadastrar recorrente", command=self.add_recurring).grid(row=0, column=5, padx=8, pady=8)
        ctk.CTkButton(rec_form, text="Desativar recorrente selecionada", command=self.deactivate_selected_recurring).grid(row=0, column=6, padx=8, pady=8)

        self.recurring_table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("categoria", "Categoria", 160),
                ("impacto", "Impacto", 160),
                ("descricao", "Descrição", 300),
                ("valor_padrao", "Valor", 120),
                ("dia_vencimento", "Dia", 80),
            ],
            height=5,
        )
        self.recurring_table.pack(fill="x", padx=PAD, pady=(0, PAD))

    def _on_category_selected(self, value: str) -> None:
        if value in CASH_ONLY_CATEGORIES:
            self.impact_var.set("Somente fluxo de caixa")
        else:
            self.impact_var.set("Entra no DRE")

    def _on_rec_category_selected(self, value: str) -> None:
        if value in CASH_ONLY_CATEGORIES:
            self.rec_impact_var.set("Somente fluxo de caixa")
        else:
            self.rec_impact_var.set("Entra no DRE")

    def add(self) -> None:
        try:
            expense_date = date.fromisoformat(self.date_var.get().strip())
            category = self.category_var.get().strip()
            description = self.description_var.get().strip()
            value = money_to_float(self.value_var.get())
            incide_dre = bool(DRE_IMPACT_OPTIONS.get(self.impact_var.get(), 1))
        except ValueError:
            messagebox.showerror("Erro", "Data ou valor inválido.")
            return
        if not category or not description or value <= 0:
            messagebox.showwarning("Atenção", "Preencha categoria, descrição e valor.")
            return
        add_expense(expense_date, category, description, value, incide_dre=incide_dre)
        self.description_var.set("")
        self.value_var.set("")
        self.month_var.set(f"{expense_date.year:04d}-{expense_date.month:02d}")
        self.refresh()

    def delete_selected_expense(self) -> None:
        selected = self.table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma saída na tabela.")
            return
        expense_id = int(selected[0])
        ok = messagebox.askyesno("Excluir saída", "Deseja excluir a saída selecionada? Ela será removida do fluxo e, se aplicável, do DRE.")
        if not ok:
            return
        deleted = delete_expense(expense_id)
        if not deleted:
            messagebox.showinfo("Saída não encontrada", "Essa saída não foi encontrada ou já foi removida.")
            return
        self.refresh()
        messagebox.showinfo("Saída excluída", "Saída removida com sucesso.")

    def add_recurring(self) -> None:
        try:
            category = self.rec_category_var.get().strip()
            description = self.rec_description_var.get().strip()
            value = money_to_float(self.rec_value_var.get())
            day = int(self.rec_day_var.get().strip())
            incide_dre = bool(DRE_IMPACT_OPTIONS.get(self.rec_impact_var.get(), 1))
        except ValueError:
            messagebox.showerror("Erro", "Valor ou dia inválido.")
            return
        if not category or not description or value <= 0 or day < 1 or day > 31:
            messagebox.showwarning("Atenção", "Preencha categoria, descrição, valor e dia entre 1 e 31.")
            return
        add_recurring_expense(category, description, value, day, incide_dre=incide_dre)
        self.rec_description_var.set("")
        self.rec_value_var.set("")
        self.rec_day_var.set("1")
        self.refresh()

    def deactivate_selected_recurring(self) -> None:
        selected = self.recurring_table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma saída recorrente na tabela.")
            return
        recurring_id = int(selected[0])
        ok = messagebox.askyesno(
            "Desativar recorrente",
            "Deseja desativar essa recorrente? Ela não será gerada nos próximos meses.\n\n"
            "Saídas já lançadas por ela continuam existindo e podem ser excluídas individualmente acima.",
        )
        if not ok:
            return
        deactivated = deactivate_recurring_expense(recurring_id)
        if not deactivated:
            messagebox.showinfo("Recorrente não encontrada", "Essa recorrente não foi encontrada ou já foi desativada.")
            return
        self.refresh()
        messagebox.showinfo("Recorrente desativada", "Saída recorrente desativada com sucesso.")

    def generate_recurring(self) -> None:
        created = generate_recurring_for_month(self.month_var.get().strip())
        messagebox.showinfo("Recorrentes", f"{created} saídas recorrentes lançadas.")
        self.refresh()

    def refresh(self) -> None:
        rows = []
        for row in list_expenses(self.month_var.get().strip()):
            impacto = "DRE + Caixa" if int(row.get("incide_dre", 1) or 0) else "Só caixa"
            rows.append({**row, "impacto": impacto, "valor": brl(row["valor"])})
        self.table.set_rows(rows)
        recurring_rows = []
        for row in list_recurring_expenses():
            impacto = "DRE + Caixa" if int(row.get("incide_dre", 1) or 0) else "Só caixa"
            recurring_rows.append({**row, "impacto": impacto, "valor_padrao": brl(row["valor_padrao"])})
        self.recurring_table.set_rows(recurring_rows)

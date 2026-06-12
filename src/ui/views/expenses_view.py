from datetime import date
from tkinter import messagebox

import customtkinter as ctk

from src.services.expenses_service import (
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


class ExpensesView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.month_var = ctk.StringVar(value=current_month_reference())
        self.date_var = ctk.StringVar(value=date.today().isoformat())
        self.category_var = ctk.StringVar(value="")
        self.description_var = ctk.StringVar(value="")
        self.value_var = ctk.StringVar(value="")
        self.rec_category_var = ctk.StringVar(value="")
        self.rec_description_var = ctk.StringVar(value="")
        self.rec_value_var = ctk.StringVar(value="")
        self.rec_day_var = ctk.StringVar(value="1")
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Despesas", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=(0, PAD))

        ctk.CTkLabel(form, text="Data:").grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.date_var, width=120).grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkLabel(form, text="Categoria:").grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.category_var, width=160).grid(row=0, column=3, padx=8, pady=8)
        ctk.CTkLabel(form, text="Descrição:").grid(row=0, column=4, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.description_var, width=260).grid(row=0, column=5, padx=8, pady=8)
        ctk.CTkLabel(form, text="Valor:").grid(row=0, column=6, padx=8, pady=8)
        ctk.CTkEntry(form, textvariable=self.value_var, width=100).grid(row=0, column=7, padx=8, pady=8)
        ctk.CTkButton(form, text="Adicionar", command=self.add).grid(row=0, column=8, padx=8, pady=8)

        controls = ctk.CTkFrame(self)
        controls.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(controls, text="Mês:").pack(side="left", padx=8, pady=8)
        ctk.CTkEntry(controls, textvariable=self.month_var, width=90).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(controls, text="Atualizar", command=self.refresh).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(controls, text="Excluir despesa selecionada", command=self.delete_selected_expense).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(controls, text="Gerar recorrentes do mês", command=self.generate_recurring).pack(side="left", padx=8, pady=8)

        self.table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("data", "Data", 110),
                ("categoria", "Categoria", 160),
                ("descricao", "Descrição", 360),
                ("valor", "Valor", 120),
            ],
            height=16,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        ctk.CTkLabel(self, text="Despesas recorrentes", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        rec_form = ctk.CTkFrame(self)
        rec_form.pack(fill="x", padx=PAD, pady=(6, PAD))
        ctk.CTkEntry(rec_form, textvariable=self.rec_category_var, width=150, placeholder_text="Categoria").grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(rec_form, textvariable=self.rec_description_var, width=260, placeholder_text="Descrição").grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkEntry(rec_form, textvariable=self.rec_value_var, width=110, placeholder_text="Valor").grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkEntry(rec_form, textvariable=self.rec_day_var, width=90, placeholder_text="Dia").grid(row=0, column=3, padx=8, pady=8)
        ctk.CTkButton(rec_form, text="Cadastrar recorrente", command=self.add_recurring).grid(row=0, column=4, padx=8, pady=8)
        ctk.CTkButton(rec_form, text="Desativar recorrente selecionada", command=self.deactivate_selected_recurring).grid(row=0, column=5, padx=8, pady=8)

        self.recurring_table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("categoria", "Categoria", 160),
                ("descricao", "Descrição", 360),
                ("valor_padrao", "Valor", 120),
                ("dia_vencimento", "Dia", 80),
            ],
            height=5,
        )
        self.recurring_table.pack(fill="x", padx=PAD, pady=(0, PAD))

    def add(self) -> None:
        try:
            expense_date = date.fromisoformat(self.date_var.get().strip())
            category = self.category_var.get().strip()
            description = self.description_var.get().strip()
            value = money_to_float(self.value_var.get())
        except ValueError:
            messagebox.showerror("Erro", "Data ou valor inválido.")
            return
        if not category or not description or value <= 0:
            messagebox.showwarning("Atenção", "Preencha categoria, descrição e valor.")
            return
        add_expense(expense_date, category, description, value)
        self.category_var.set("")
        self.description_var.set("")
        self.value_var.set("")
        self.month_var.set(f"{expense_date.year:04d}-{expense_date.month:02d}")
        self.refresh()

    def delete_selected_expense(self) -> None:
        selected = self.table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma despesa na tabela.")
            return
        expense_id = int(selected[0])
        ok = messagebox.askyesno("Excluir despesa", "Deseja excluir a despesa selecionada? Essa ação remove o valor do DRE.")
        if not ok:
            return
        deleted = delete_expense(expense_id)
        if not deleted:
            messagebox.showinfo("Despesa não encontrada", "Essa despesa não foi encontrada ou já foi removida.")
            return
        self.refresh()
        messagebox.showinfo("Despesa excluída", "Despesa removida com sucesso.")

    def add_recurring(self) -> None:
        try:
            category = self.rec_category_var.get().strip()
            description = self.rec_description_var.get().strip()
            value = money_to_float(self.rec_value_var.get())
            day = int(self.rec_day_var.get().strip())
        except ValueError:
            messagebox.showerror("Erro", "Valor ou dia inválido.")
            return
        if not category or not description or value <= 0 or day < 1 or day > 31:
            messagebox.showwarning("Atenção", "Preencha categoria, descrição, valor e dia entre 1 e 31.")
            return
        add_recurring_expense(category, description, value, day)
        self.rec_category_var.set("")
        self.rec_description_var.set("")
        self.rec_value_var.set("")
        self.rec_day_var.set("1")
        self.refresh()

    def deactivate_selected_recurring(self) -> None:
        selected = self.recurring_table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma despesa recorrente na tabela.")
            return
        recurring_id = int(selected[0])
        ok = messagebox.askyesno(
            "Desativar recorrente",
            "Deseja desativar essa recorrente? Ela não será gerada nos próximos meses.\n\n"
            "Despesas já lançadas por ela continuam existindo e podem ser excluídas individualmente acima.",
        )
        if not ok:
            return
        deactivated = deactivate_recurring_expense(recurring_id)
        if not deactivated:
            messagebox.showinfo("Recorrente não encontrada", "Essa recorrente não foi encontrada ou já foi desativada.")
            return
        self.refresh()
        messagebox.showinfo("Recorrente desativada", "Despesa recorrente desativada com sucesso.")

    def generate_recurring(self) -> None:
        created = generate_recurring_for_month(self.month_var.get().strip())
        messagebox.showinfo("Recorrentes", f"{created} despesas recorrentes lançadas.")
        self.refresh()

    def refresh(self) -> None:
        rows = []
        for row in list_expenses(self.month_var.get().strip()):
            rows.append({**row, "valor": brl(row["valor"])})
        self.table.set_rows(rows)
        recurring_rows = []
        for row in list_recurring_expenses():
            recurring_rows.append({**row, "valor_padrao": brl(row["valor_padrao"])})
        self.recurring_table.set_rows(recurring_rows)

from datetime import date
from tkinter import messagebox

import customtkinter as ctk

from src.database import init_database
from src.services.cancellations_service import (
    delete_cancelled_order,
    list_cancelled_orders,
    register_cancelled_order,
)
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl


class CancellationsView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.order_id_var = ctk.StringVar(value="")
        self.date_var = ctk.StringVar(value=date.today().isoformat())
        self.reason_var = ctk.StringVar(value="")
        self.status_var = ctk.StringVar(value="Cadastre o ID do pedido cancelado. O app dará baixa pelo valor já conhecido do pedido.")
        self._build()
        self.refresh()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Cancelamentos por Pedido", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=PAD, pady=(0, PAD))
        ctk.CTkLabel(form, text="ID do pedido:").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.order_id_var, width=220).grid(row=0, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(form, text="Data:").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.date_var, width=130).grid(row=0, column=3, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(form, text="Motivo:").grid(row=0, column=4, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(form, textvariable=self.reason_var, width=280).grid(row=0, column=5, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(form, text="Cadastrar baixa", command=self.add_cancellation).grid(row=0, column=6, padx=8, pady=8)
        ctk.CTkButton(form, text="Excluir baixa selecionada", command=self.delete_selected).grid(row=0, column=7, padx=8, pady=8)
        form.grid_columnconfigure(5, weight=1)

        ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            text_color="gray",
            wraplength=980,
            justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

        self.table = SimpleTable(
            self,
            [
                ("pedido_id", "Pedido", 180),
                ("data_cancelamento", "Data", 110),
                ("valor_baixado", "Valor baixado", 130),
                ("status_anterior", "Status anterior", 140),
                ("status_atual", "Status atual", 130),
                ("motivo", "Motivo", 300),
                ("criado_em", "Cadastrado em", 160),
            ],
            height=18,
        )
        self.table.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        ctk.CTkLabel(
            self,
            text="Regra: pedido cancelado sai de Aberto futuro/Shopee em espera. Se o ID ainda não existir na base, fica pendente e será aplicado quando o pedido aparecer em uma importação futura.",
            text_color="gray",
            wraplength=980,
            justify="left",
        ).pack(anchor="w", padx=PAD, pady=(0, PAD))

    def add_cancellation(self) -> None:
        pedido_id = self.order_id_var.get().strip()
        if not pedido_id:
            messagebox.showwarning("Atenção", "Informe o ID do pedido.")
            return
        try:
            cancel_date = date.fromisoformat(self.date_var.get().strip())
        except ValueError:
            messagebox.showerror("Data inválida", "Use o formato AAAA-MM-DD.")
            return

        try:
            init_database()
            result = register_cancelled_order(pedido_id, cancel_date, self.reason_var.get().strip())
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível cadastrar o cancelamento:\n{exc}")
            return

        if result["encontrado"]:
            self.status_var.set(
                f"Pedido {result['pedido_id']} baixado. "
                f"Status anterior: {result['status_anterior']}. "
                f"Valor retirado da esteira: {brl(result['valor_baixado'])}."
            )
        else:
            self.status_var.set(
                f"Pedido {result['pedido_id']} cadastrado como cancelamento pendente. "
                "Quando ele aparecer em uma importação, o app dará baixa automaticamente."
            )
        self.order_id_var.set("")
        self.reason_var.set("")
        self.refresh()

    def delete_selected(self) -> None:
        selected = self.table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione um cancelamento na tabela.")
            return
        pedido_id = selected[0]
        ok = messagebox.askyesno("Excluir baixa", f"Remover a baixa manual do pedido {pedido_id}?")
        if not ok:
            return
        try:
            removed = delete_cancelled_order(pedido_id)
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível excluir:\n{exc}")
            return
        if removed:
            self.status_var.set(f"Baixa do pedido {pedido_id} removida.")
        else:
            self.status_var.set("Baixa não encontrada.")
        self.refresh()

    def refresh(self) -> None:
        try:
            init_database()
            rows = []
            for row in list_cancelled_orders():
                rows.append({**row, "valor_baixado": brl(row.get("valor_baixado"))})
            self.table.set_rows(rows)
        except Exception as exc:
            self.status_var.set(f"Erro ao carregar cancelamentos: {exc}")

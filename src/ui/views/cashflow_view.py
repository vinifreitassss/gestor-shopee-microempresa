from datetime import date
from tkinter import messagebox

import customtkinter as ctk

from src.database import init_database
from src.services.cashflow_service import (
    get_cashflow_summary,
    get_initial_position,
    save_initial_position,
)
from src.services.reports_service import current_month_reference
from src.ui.components import MetricCard
from src.ui.theme import PAD
from src.utils import brl, money_to_float, percent


class CashFlowView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        today = date.today().isoformat()
        self.month_var = ctk.StringVar(value=current_month_reference())
        self.cutoff_var = ctk.StringVar(value=today)
        self.bank_var = ctk.StringVar(value="0")
        self.shopee_cash_var = ctk.StringVar(value="0")
        self.shopee_waiting_var = ctk.StringVar(value="0")
        self.cards = {}
        self.status_var = ctk.StringVar(value="")
        self._build()
        self._ensure_database_ready()
        self._load_initial_position()

    def _ensure_database_ready(self) -> None:
        try:
            init_database()
        except Exception as exc:
            self.status_var.set(f"Erro ao preparar banco do fluxo de caixa: {exc}")

    def _build(self) -> None:
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=PAD, pady=PAD)

        ctk.CTkLabel(
            header,
            text="Fluxo de Caixa",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")

        ctk.CTkLabel(header, text="Mês:").pack(side="left", padx=(24, 6))
        ctk.CTkEntry(header, textvariable=self.month_var, width=90).pack(side="left", padx=6)
        ctk.CTkButton(header, text="Atualizar", command=self.refresh).pack(side="left", padx=8)

        self._build_initial_position_box()
        self._build_metric_cards()

        self.info_label = ctk.CTkLabel(
            self,
            text="Pedidos sem rastreio ficam como aberto futuro; pedidos com rastreio entram em Shopee em espera.",
            text_color="gray",
        )
        self.info_label.pack(anchor="w", padx=PAD, pady=(0, 6))

        self.status_label = ctk.CTkLabel(self, textvariable=self.status_var, text_color="gray")
        self.status_label.pack(anchor="w", padx=PAD, pady=(0, PAD))

    def _build_initial_position_box(self) -> None:
        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=(0, PAD))

        ctk.CTkLabel(
            box,
            text="Posição inicial do controle",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=8, padx=8, pady=(8, 2), sticky="w")

        ctk.CTkLabel(box, text="Data de corte:").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkEntry(box, textvariable=self.cutoff_var, width=120).grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(box, text="Banco:").grid(row=1, column=2, padx=8, pady=8)
        ctk.CTkEntry(box, textvariable=self.bank_var, width=110).grid(row=1, column=3, padx=8, pady=8)

        ctk.CTkLabel(box, text="Caixa Shopee:").grid(row=1, column=4, padx=8, pady=8)
        ctk.CTkEntry(box, textvariable=self.shopee_cash_var, width=110).grid(row=1, column=5, padx=8, pady=8)

        ctk.CTkLabel(box, text="Shopee em espera:").grid(row=1, column=6, padx=8, pady=8)
        ctk.CTkEntry(box, textvariable=self.shopee_waiting_var, width=110).grid(row=1, column=7, padx=8, pady=8)

        ctk.CTkButton(box, text="Salvar posição inicial", command=self.save_position).grid(row=1, column=8, padx=8, pady=8)

    def _build_metric_cards(self) -> None:
        metrics = ctk.CTkFrame(self)
        metrics.pack(fill="x", padx=PAD, pady=(0, PAD))

        metric_defs = [
            ("saldo_banco", "Banco"),
            ("saldo_shopee_disponivel", "Caixa Shopee"),
            ("saldo_shopee_espera", "Shopee em espera"),
            ("saldo_possivel_aberto", "Aberto futuro"),
            ("pedidos_em_aberto", "Pedidos sem rastreio"),
            ("caixa_disponivel", "Caixa disponível"),
            ("caixa_livre_estimado", "Caixa livre estimado"),
            ("saques", "Transferido no mês"),
            ("despesas", "Despesas no mês"),
            ("imposto_reservado", "Imposto reservado"),
            ("taxa_total_percentual", "Taxa média Shopee"),
            ("tempo_liberacao_medio", "Tempo médio liberação"),
        ]

        for idx, (key, title) in enumerate(metric_defs):
            card = MetricCard(metrics, title)
            card.grid(row=idx // 4, column=idx % 4, sticky="ew", padx=6, pady=6)
            metrics.grid_columnconfigure(idx % 4, weight=1)
            self.cards[key] = card

    def _load_initial_position(self) -> None:
        try:
            position = get_initial_position()
        except Exception as exc:
            self.status_var.set(f"Não consegui carregar a posição inicial: {exc}")
            return

        if position:
            self.cutoff_var.set(position["data_corte"])
            self.bank_var.set(brl(position["saldo_banco"]).replace("R$ ", ""))
            self.shopee_cash_var.set(brl(position["saldo_shopee_disponivel"]).replace("R$ ", ""))
            self.shopee_waiting_var.set(brl(position["saldo_shopee_espera"]).replace("R$ ", ""))

        self.refresh()

    def save_position(self) -> None:
        try:
            init_database()
            data_corte = date.fromisoformat(self.cutoff_var.get().strip())
            saldo_banco = money_to_float(self.bank_var.get())
            saldo_shopee = money_to_float(self.shopee_cash_var.get())
            saldo_espera = money_to_float(self.shopee_waiting_var.get())
        except ValueError:
            messagebox.showerror("Erro", "Use data AAAA-MM-DD e valores numéricos válidos.")
            return
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível preparar o fluxo de caixa:\n{exc}")
            return

        save_initial_position(data_corte, saldo_banco, saldo_shopee, saldo_espera)
        messagebox.showinfo("Posição inicial", "Posição inicial salva com sucesso.")
        self.refresh()

    def refresh(self) -> None:
        try:
            init_database()
            month = self.month_var.get().strip()
            summary = get_cashflow_summary(month)
        except Exception as exc:
            self.status_var.set(f"Erro ao atualizar fluxo de caixa: {exc}")
            for card in self.cards.values():
                card.set_value("-")
            return

        self.status_var.set("")
        money_fields = {
            "saldo_banco",
            "saldo_shopee_disponivel",
            "saldo_shopee_espera",
            "saldo_possivel_aberto",
            "caixa_disponivel",
            "caixa_livre_estimado",
            "saques",
            "despesas",
            "imposto_reservado",
        }

        for key, card in self.cards.items():
            value = summary.get(key)
            if key in money_fields:
                card.set_value(brl(value))
            elif key == "taxa_total_percentual":
                card.set_value(percent(value))
            elif key == "tempo_liberacao_medio":
                card.set_value(f"{float(value or 0):.1f} dias".replace(".", ","))
            else:
                card.set_value(str(value or "-"))

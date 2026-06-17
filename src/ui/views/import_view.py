from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.importer import ShopeeImportError, ShopeeImporter
from src.services.financial_import_service import (
    find_financial_importations_same_period,
    preview_financial_importation,
    save_financial_importation,
)
from src.services.import_service import (
    delete_importation,
    find_importations_same_month,
    find_importations_same_period,
    list_importations,
    save_importation,
)
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl, mes_referencia_from_date


REPORT_OPTIONS = {
    "Vendas / desempenho": "performance",
    "Pedidos a enviar / consolidar": "pedidos_enviados",
    "Pagamentos / saques Shopee": "pagamentos_shopee",
}


class ImportView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        yesterday = date.today() - timedelta(days=1)
        self.file_path_var = ctk.StringVar(value="")
        self.report_label_var = ctk.StringVar(value="Vendas / desempenho")
        self.tipo_var = ctk.StringVar(value="diario")
        self.data_inicio_var = ctk.StringVar(value=yesterday.isoformat())
        self.data_fim_var = ctk.StringVar(value=yesterday.isoformat())
        self.status_var = ctk.StringVar(value="Nenhuma planilha selecionada.")
        self.summary_var = ctk.StringVar(value="Escolha uma planilha e confira o tipo antes de confirmar.")
        self.preview_lines = []
        self._build()
        self._bind_summary_updates()
        self.update_import_summary()
        self.refresh()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Importações Shopee", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)

        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=(0, PAD))
        box.grid_columnconfigure(1, weight=1)
        box.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(box, text="Escolher planilha", command=self.choose_file).grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.file_path_var, width=760).grid(row=0, column=1, columnspan=3, padx=8, pady=8, sticky="ew")

        ctk.CTkLabel(box, text="Tipo de planilha:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=8, pady=8, sticky="w")
        self.report_menu = ctk.CTkOptionMenu(
            box,
            variable=self.report_label_var,
            values=list(REPORT_OPTIONS.keys()),
            width=260,
            command=lambda _value: self.update_import_summary(),
        )
        self.report_menu.grid(row=1, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(box, text="Período:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=2, padx=8, pady=8, sticky="e")
        self.tipo_menu = ctk.CTkOptionMenu(
            box,
            variable=self.tipo_var,
            values=["diario", "mensal", "personalizado"],
            width=180,
            command=lambda _value: self.update_import_summary(),
        )
        self.tipo_menu.grid(row=1, column=3, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(box, text="Data início:").grid(row=2, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(box, textvariable=self.data_inicio_var, width=140).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, text="Data fim / envio:").grid(row=2, column=2, padx=8, pady=8, sticky="e")
        ctk.CTkEntry(box, textvariable=self.data_fim_var, width=140).grid(row=2, column=3, padx=8, pady=8, sticky="w")

        action_row = ctk.CTkFrame(box)
        action_row.grid(row=3, column=0, columnspan=4, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(action_row, text="Pré-visualizar", command=self.preview).pack(side="left", padx=(0, 8), pady=4)
        ctk.CTkButton(action_row, text="Confirmar e plugar no app", command=self.confirm_import).pack(side="left", padx=8, pady=4)
        ctk.CTkButton(action_row, text="Excluir selecionada", command=self.delete_selected_importation).pack(side="left", padx=8, pady=4)
        ctk.CTkLabel(action_row, textvariable=self.status_var, text_color="gray", wraplength=560, justify="left").pack(side="left", padx=16, pady=4)

        ctk.CTkLabel(
            box,
            textvariable=self.summary_var,
            text_color="#f6c343",
            font=ctk.CTkFont(size=13, weight="bold"),
            wraplength=980,
            justify="left",
        ).grid(row=4, column=0, columnspan=4, padx=8, pady=(0, 10), sticky="w")

        ctk.CTkLabel(self, text="Prévia da planilha", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.preview_table = SimpleTable(
            self,
            [
                ("pedido_id", "Pedido / Produto", 180),
                ("status", "Status", 160),
                ("data", "Data", 140),
                ("valor", "Valor bruto", 130),
                ("liquido", "Líquido / saldo", 130),
                ("obs", "Obs.", 220),
            ],
            height=9,
        )
        self.preview_table.pack(fill="both", expand=True, padx=PAD, pady=(6, PAD))

        ctk.CTkLabel(self, text="Importações recentes", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.history_table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("arquivo_nome", "Arquivo", 240),
                ("tipo_relatorio", "Relatório", 150),
                ("tipo_periodo", "Tipo", 100),
                ("data_inicio", "Início", 100),
                ("data_fim", "Fim", 100),
                ("mes_referencia", "Mês", 90),
                ("status", "Status", 100),
                ("criado_em", "Criado em", 150),
            ],
            height=6,
        )
        self.history_table.pack(fill="both", padx=PAD, pady=(6, PAD))

    def _bind_summary_updates(self) -> None:
        for var in (self.file_path_var, self.report_label_var, self.tipo_var, self.data_inicio_var, self.data_fim_var):
            var.trace_add("write", lambda *_: self.update_import_summary())

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(title="Escolha a planilha Shopee", filetypes=[("Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")])
        if path:
            self.file_path_var.set(path)
            self.status_var.set(f"Selecionado: {Path(path).name}")
            self.update_import_summary()

    def _report_type(self) -> str:
        return REPORT_OPTIONS[self.report_label_var.get()]

    def update_import_summary(self) -> None:
        path = self.file_path_var.get().strip()
        arquivo = Path(path).name if path else "nenhuma planilha escolhida"
        report_label = self.report_label_var.get()
        tipo = self.tipo_var.get().strip()
        data_inicio = self.data_inicio_var.get().strip()
        data_fim = self.data_fim_var.get().strip()
        extra = ""
        if REPORT_OPTIONS.get(report_label) == "pedidos_enviados":
            extra = " | modo: consolidar snapshot diário, sem substituir histórico"
        self.summary_var.set(
            "Esta planilha será plugada no app como: "
            f"{report_label} | período {tipo} | de {data_inicio} até {data_fim} | arquivo: {arquivo}{extra}"
        )

    def preview(self) -> None:
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha uma planilha primeiro.")
            return
        report_type = self._report_type()
        try:
            if report_type == "performance":
                self._preview_performance(path)
            else:
                data_fim = date.fromisoformat(self.data_fim_var.get().strip())
                self._preview_financial(path, report_type, data_fim)
        except ShopeeImportError as exc:
            messagebox.showerror("Erro ao ler planilha", str(exc))
        except ValueError:
            messagebox.showerror("Data inválida", "Use o formato AAAA-MM-DD, exemplo: 2026-06-11.")

    def _preview_performance(self, path: str) -> None:
        self.preview_lines = ShopeeImporter().preview(path)
        rows = []
        for line in self.preview_lines:
            if not line.contabilizar:
                continue
            rows.append({"pedido_id": line.produto_nome, "status": line.variacao_nome, "data": "", "valor": brl(line.vendas_pedido_pago), "liquido": "", "obs": f"{line.unidades_pedido_pago} un."})
        self.preview_table.set_rows(rows)
        self.status_var.set(f"{len(rows)} variações vendidas encontradas.")

    def _preview_financial(self, path: str, report_type: str, data_envio_real: date) -> None:
        preview = preview_financial_importation(path, report_type, data_envio_real=data_envio_real)
        rows = [{**row, "valor": brl(row.get("valor")), "liquido": brl(row.get("liquido"))} for row in preview["rows"]]
        self.preview_table.set_rows(rows)
        if report_type == "pedidos_enviados":
            self.status_var.set(
                f"{preview['count']} pedidos no snapshot. Todos entram/ficam em aberto futuro: "
                f"{brl(preview.get('saldo_possivel_aberto', 0))}. "
                "Pedidos abertos que sumirem no próximo snapshot serão movidos para Shopee em espera."
            )
        else:
            self.status_var.set(
                f"{preview['count']} transações. Entradas: {brl(preview['valor_total'])}. "
                f"Saques: {brl(preview.get('saques', preview.get('taxas', 0)))}. "
                f"Ads: {brl(preview.get('ads', 0))}. Ajustes: {brl(preview.get('ajustes_pedido', 0))}."
            )

    def confirm_import(self) -> None:
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha uma planilha primeiro.")
            return
        try:
            data_inicio = date.fromisoformat(self.data_inicio_var.get().strip())
            data_fim = date.fromisoformat(self.data_fim_var.get().strip())
        except ValueError:
            messagebox.showerror("Data inválida", "Use o formato AAAA-MM-DD, exemplo: 2026-06-11.")
            return

        tipo = self.tipo_var.get().strip()
        report_label = self.report_label_var.get()
        report_type = self._report_type()
        mes_ref = mes_referencia_from_date(data_inicio)
        mode = "somar"
        duplicates = []

        if report_type == "pedidos_enviados":
            replacement_text = (
                "\n\nModo consolidação: esta planilha NÃO substituirá as antigas. "
                "Ela atualiza pedidos atuais como aberto futuro e move para em espera os pedidos abertos que sumiram do snapshot."
            )
        else:
            if tipo == "mensal":
                duplicates = find_importations_same_month(report_type, tipo, mes_ref)
            else:
                duplicates = find_importations_same_period(tipo, data_inicio, data_fim) if report_type == "performance" else find_financial_importations_same_period(report_type, tipo, data_inicio, data_fim)
            replacement_text = ""
            if duplicates:
                replacement_text = f"\n\nAtenção: serão substituída(s) {len(duplicates)} importação(ões) anterior(es) desse mesmo tipo/período."

        ok = messagebox.askyesno(
            "Confirmar importação",
            "Deseja plugar esta planilha no app?\n\n"
            f"Arquivo: {Path(path).name}\n"
            f"Tipo de planilha: {report_label}\n"
            f"Período: {tipo}\n"
            f"Data início: {data_inicio.isoformat()}\n"
            f"Data fim/envio: {data_fim.isoformat()}\n"
            f"Mês de referência: {mes_ref}"
            f"{replacement_text}",
        )
        if not ok:
            return

        replaced_count = 0
        for duplicate in duplicates:
            delete_importation(int(duplicate["id"]))
            replaced_count += 1

        try:
            if report_type == "performance":
                import_id = save_importation(path, tipo, data_inicio, data_fim, mode=mode)
            else:
                import_id = save_financial_importation(path, report_type, tipo, data_inicio, data_fim, mode=mode)
            message = f"Importação salva com ID {import_id}."
            if report_type == "pedidos_enviados":
                message += "\n\nConsolidação aplicada. Histórico anterior preservado."
            if replaced_count:
                message += f"\n\nSubstituiu {replaced_count} importação(ões) anterior(es)."
            messagebox.showinfo("Importação concluída", message)
            self.status_var.set(message.replace("\n", " "))
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível importar:\n{exc}")

    def delete_selected_importation(self) -> None:
        selected = self.history_table.selected_values()
        if not selected:
            messagebox.showwarning("Atenção", "Selecione uma importação na tabela de histórico.")
            return
        try:
            importacao_id = int(selected[0])
        except (TypeError, ValueError):
            messagebox.showerror("Erro", "Não consegui identificar o ID da importação selecionada.")
            return
        confirm = messagebox.askyesno("Excluir importação", f"Excluir a importação ID {importacao_id}?\n\nOs dados gerados por essa planilha serão removidos do sistema.")
        if not confirm:
            return
        try:
            deleted = delete_importation(importacao_id)
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível excluir:\n{exc}")
            return
        if not deleted:
            messagebox.showwarning("Atenção", "Importação não encontrada.")
            return
        self.status_var.set(f"Importação ID {importacao_id} excluída.")
        self.refresh()

    def refresh(self) -> None:
        rows = list_importations()
        self.history_table.set_rows(rows)

from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.importer import ShopeeImportError, ShopeeImporter
from src.services.import_service import find_importations_same_period, save_importation
from src.services.products_service import list_importations
from src.ui.components import SimpleTable
from src.ui.theme import PAD
from src.utils import brl


class ImportView(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        yesterday = date.today() - timedelta(days=1)
        self.file_path_var = ctk.StringVar(value="")
        self.tipo_var = ctk.StringVar(value="diario")
        self.data_inicio_var = ctk.StringVar(value=yesterday.isoformat())
        self.data_fim_var = ctk.StringVar(value=yesterday.isoformat())
        self.status_var = ctk.StringVar(value="Nenhuma planilha selecionada.")
        self.preview_lines = []
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Importações Shopee", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=PAD, pady=PAD)

        box = ctk.CTkFrame(self)
        box.pack(fill="x", padx=PAD, pady=(0, PAD))

        ctk.CTkButton(box, text="Escolher planilha", command=self.choose_file).grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(box, textvariable=self.file_path_var, width=520).grid(row=0, column=1, columnspan=4, padx=8, pady=8, sticky="ew")

        ctk.CTkLabel(box, text="Tipo:").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkOptionMenu(box, variable=self.tipo_var, values=["diario", "mensal", "personalizado"]).grid(row=1, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, text="Data início:").grid(row=1, column=2, padx=8, pady=8, sticky="e")
        ctk.CTkEntry(box, textvariable=self.data_inicio_var, width=120).grid(row=1, column=3, padx=8, pady=8)
        ctk.CTkLabel(box, text="Data fim:").grid(row=1, column=4, padx=8, pady=8, sticky="e")
        ctk.CTkEntry(box, textvariable=self.data_fim_var, width=120).grid(row=1, column=5, padx=8, pady=8)

        ctk.CTkButton(box, text="Pré-visualizar", command=self.preview).grid(row=2, column=0, padx=8, pady=8)
        ctk.CTkButton(box, text="Confirmar importação", command=self.confirm_import).grid(row=2, column=1, padx=8, pady=8, sticky="w")
        ctk.CTkLabel(box, textvariable=self.status_var).grid(row=2, column=2, columnspan=4, padx=8, pady=8, sticky="w")
        box.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Prévia das variações vendidas", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.preview_table = SimpleTable(
            self,
            [
                ("produto_nome", "Produto pai", 320),
                ("variacao_nome", "Variação", 260),
                ("unidades", "Unidades", 90),
                ("faturamento", "Faturamento", 130),
                ("tipo_linha", "Tipo", 110),
                ("contabilizar", "Conta?", 80),
            ],
            height=9,
        )
        self.preview_table.pack(fill="both", expand=True, padx=PAD, pady=(6, PAD))

        ctk.CTkLabel(self, text="Importações recentes", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=PAD)
        self.history_table = SimpleTable(
            self,
            [
                ("id", "ID", 60),
                ("arquivo_nome", "Arquivo", 260),
                ("tipo_periodo", "Tipo", 100),
                ("data_inicio", "Início", 100),
                ("data_fim", "Fim", 100),
                ("mes_referencia", "Mês", 90),
                ("status", "Status", 100),
            ],
            height=6,
        )
        self.history_table.pack(fill="both", padx=PAD, pady=(6, PAD))

    def choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Escolha a planilha Shopee",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Todos os arquivos", "*.*")],
        )
        if path:
            self.file_path_var.set(path)
            self.status_var.set(f"Selecionado: {Path(path).name}")

    def preview(self) -> None:
        path = self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Atenção", "Escolha uma planilha primeiro.")
            return
        try:
            self.preview_lines = ShopeeImporter().preview(path)
            rows = []
            for line in self.preview_lines:
                if not line.contabilizar:
                    continue
                rows.append(
                    {
                        "produto_nome": line.produto_nome,
                        "variacao_nome": line.variacao_nome,
                        "unidades": line.unidades_pedido_pago,
                        "faturamento": brl(line.vendas_pedido_pago),
                        "tipo_linha": line.tipo_linha,
                        "contabilizar": "Sim" if line.contabilizar else "Não",
                    }
                )
            self.preview_table.set_rows(rows)
            self.status_var.set(f"{len(rows)} variações vendidas encontradas.")
        except ShopeeImportError as exc:
            messagebox.showerror("Erro ao ler planilha", str(exc))

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
        duplicates = find_importations_same_period(tipo, data_inicio, data_fim)
        mode = "somar"
        if duplicates:
            replace = messagebox.askyesno(
                "Importação já existe",
                "Já existe importação confirmada para esse período.\n\nSim = substituir anterior\nNão = cancelar",
            )
            if not replace:
                return
            mode = "substituir"

        try:
            import_id = save_importation(path, tipo, data_inicio, data_fim, mode=mode)
            messagebox.showinfo("Importação concluída", f"Importação salva com ID {import_id}.")
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Erro", f"Não foi possível importar:\n{exc}")

    def refresh(self) -> None:
        rows = list_importations()
        self.history_table.set_rows(rows)

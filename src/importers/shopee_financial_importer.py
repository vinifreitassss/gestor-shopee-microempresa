from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.importer import ShopeeImportError
from src.utils import int_to_safe, money_to_float, normalize_text


@dataclass
class FinancialOrderItem:
    pedido_id: str
    produto_nome: str
    sku: str
    variacao_nome: str
    quantidade: int
    subtotal_produto: float


@dataclass
class FinancialOrder:
    pedido_id: str
    status_pedido: str
    data_criacao: str
    data_pagamento: str
    data_prevista_envio: str
    data_envio_real: str
    valor_total: float
    total_global: float
    taxa_transacao: float
    comissao_bruta: float
    comissao_liquida: float
    taxa_servico_bruta: float
    taxa_servico_liquida: float
    valor_liquido_estimado: float
    itens: list[FinancialOrderItem] = field(default_factory=list)


@dataclass
class BalanceTransaction:
    data_movimento: str
    tipo_transacao: str
    descricao: str
    pedido_id: str
    direcao: str
    valor: float
    status: str
    balanca_apos_transacoes: float
    valor_ajustado: float

    @property
    def is_saque(self) -> bool:
        text = normalize_text(f"{self.tipo_transacao} {self.descricao}")
        return "saque" in text or "withdraw" in text

    @property
    def is_entrada_com_pedido(self) -> bool:
        return bool(self.pedido_id) and normalize_text(self.direcao) == "entrada" and not self.is_saque


class ShopeeFinancialImporter:
    """Leitor dos relatórios financeiros da Shopee.

    - Pedidos enviados/a enviar: cria recebíveis em espera, deduplicados por ID do pedido.
    - Relatório de pagamento: confirma entradas liberadas e saques.
    """

    ORDER_COLUMNS = {
        "pedido_id": ("id do pedido", "order id"),
        "status_pedido": ("status do pedido", "order status"),
        "data_prevista_envio": ("data prevista de envio", "ship by date"),
        "data_criacao": ("data de criacao do pedido", "data de criação do pedido", "order creation date"),
        "data_pagamento": ("hora do pagamento do pedido", "payment time", "data de pagamento"),
        "produto_nome": ("nome do produto", "produto", "product name"),
        "sku": ("numero de referencia sku", "nº de referencia do sku principal", "sku", "seller sku"),
        "variacao_nome": ("nome da variacao", "nome da variação", "variation name"),
        "quantidade": ("quantidade", "quantity"),
        "subtotal_produto": ("subtotal do produto", "product subtotal"),
        "valor_total": ("valor total", "total amount"),
        "taxa_transacao": ("taxa de transacao", "taxa de transação", "transaction fee"),
        "comissao_bruta": ("taxa de comissao bruta", "taxa de comissão bruta"),
        "comissao_liquida": ("taxa de comissao liquida", "taxa de comissão líquida"),
        "taxa_servico_bruta": ("taxa de servico bruta", "taxa de serviço bruta"),
        "taxa_servico_liquida": ("taxa de servico liquida", "taxa de serviço líquida"),
        "total_global": ("total global", "grand total"),
    }

    TRANSACTION_COLUMNS = {
        "data_movimento": ("data", "date"),
        "tipo_transacao": ("tipo de transacao", "tipo de transação", "transaction type"),
        "descricao": ("descricao", "descrição", "description"),
        "pedido_id": ("id do pedido", "order id"),
        "direcao": ("direcao do dinheiro", "direção do dinheiro", "money flow"),
        "valor": ("valor", "amount"),
        "status": ("status",),
        "balanca_apos_transacoes": (
            "balanca apos as transacoes",
            "balança após as transações",
            "balance after transaction",
        ),
        "valor_ajustado": ("valor a ser ajustado", "adjustment amount"),
    }

    def preview_orders(self, file_path: str | Path, data_envio_real: date | None = None) -> list[FinancialOrder]:
        path = self._validate_path(file_path)
        df = self._read_with_detected_header(path, self.ORDER_COLUMNS, minimum_score=5)
        mapping = self._map_columns(df.columns, self.ORDER_COLUMNS)
        self._require(mapping, ["pedido_id", "valor_total", "total_global"])

        orders: dict[str, FinancialOrder] = {}
        for _, row in df.iterrows():
            pedido_id = self._get(row, mapping, "pedido_id")
            if not pedido_id:
                continue

            item = FinancialOrderItem(
                pedido_id=pedido_id,
                produto_nome=self._get(row, mapping, "produto_nome"),
                sku=self._get(row, mapping, "sku"),
                variacao_nome=self._get(row, mapping, "variacao_nome") or "Sem variação",
                quantidade=int_to_safe(self._get(row, mapping, "quantidade")),
                subtotal_produto=money_to_float(self._get(row, mapping, "subtotal_produto")),
            )

            if pedido_id not in orders:
                total_global = money_to_float(self._get(row, mapping, "total_global"))
                taxa_transacao = money_to_float(self._get(row, mapping, "taxa_transacao"))
                comissao_liquida = money_to_float(self._get(row, mapping, "comissao_liquida"))
                taxa_servico_liquida = money_to_float(self._get(row, mapping, "taxa_servico_liquida"))
                liquido = round(total_global - taxa_transacao - comissao_liquida - taxa_servico_liquida, 2)
                orders[pedido_id] = FinancialOrder(
                    pedido_id=pedido_id,
                    status_pedido=self._get(row, mapping, "status_pedido"),
                    data_criacao=self._to_iso_datetime(self._get(row, mapping, "data_criacao")),
                    data_pagamento=self._to_iso_datetime(self._get(row, mapping, "data_pagamento")),
                    data_prevista_envio=self._to_iso_datetime(self._get(row, mapping, "data_prevista_envio")),
                    data_envio_real=data_envio_real.isoformat() if data_envio_real else "",
                    valor_total=money_to_float(self._get(row, mapping, "valor_total")),
                    total_global=total_global,
                    taxa_transacao=taxa_transacao,
                    comissao_bruta=money_to_float(self._get(row, mapping, "comissao_bruta")),
                    comissao_liquida=comissao_liquida,
                    taxa_servico_bruta=money_to_float(self._get(row, mapping, "taxa_servico_bruta")),
                    taxa_servico_liquida=taxa_servico_liquida,
                    valor_liquido_estimado=liquido,
                    itens=[],
                )

            if item.produto_nome:
                orders[pedido_id].itens.append(item)

        if not orders:
            raise ShopeeImportError("Nenhum pedido financeiro foi encontrado na planilha.")
        return list(orders.values())

    def preview_transactions(self, file_path: str | Path) -> list[BalanceTransaction]:
        path = self._validate_path(file_path)
        df = self._read_with_detected_header(path, self.TRANSACTION_COLUMNS, minimum_score=4)
        mapping = self._map_columns(df.columns, self.TRANSACTION_COLUMNS)
        self._require(mapping, ["data_movimento", "tipo_transacao", "valor"])

        transactions: list[BalanceTransaction] = []
        for _, row in df.iterrows():
            data_movimento = self._to_iso_datetime(self._get(row, mapping, "data_movimento"))
            tipo_transacao = self._get(row, mapping, "tipo_transacao")
            if not data_movimento or not tipo_transacao:
                continue

            transactions.append(
                BalanceTransaction(
                    data_movimento=data_movimento,
                    tipo_transacao=tipo_transacao,
                    descricao=self._get(row, mapping, "descricao"),
                    pedido_id=self._get(row, mapping, "pedido_id"),
                    direcao=self._get(row, mapping, "direcao"),
                    valor=money_to_float(self._get(row, mapping, "valor")),
                    status=self._get(row, mapping, "status"),
                    balanca_apos_transacoes=money_to_float(self._get(row, mapping, "balanca_apos_transacoes")),
                    valor_ajustado=money_to_float(self._get(row, mapping, "valor_ajustado")),
                )
            )

        if not transactions:
            raise ShopeeImportError("Nenhuma transação foi encontrada na planilha.")
        return transactions

    def _validate_path(self, file_path: str | Path) -> Path:
        path = Path(file_path)
        if not path.exists():
            raise ShopeeImportError(f"Arquivo não encontrado: {path}")
        return path

    def _read_with_detected_header(
        self,
        path: Path,
        rules: dict[str, tuple[str, ...]],
        minimum_score: int,
    ) -> pd.DataFrame:
        try:
            excel = pd.ExcelFile(path, engine="openpyxl")
        except Exception as exc:
            raise ShopeeImportError(f"Não consegui abrir a planilha: {exc}") from exc

        best_df: pd.DataFrame | None = None
        best_score = -1
        for sheet_name in excel.sheet_names:
            raw = pd.read_excel(path, sheet_name=sheet_name, header=None, engine="openpyxl")
            header_row, score = self._detect_header_row(raw, rules)
            if score > best_score:
                best_score = score
                if header_row is None:
                    best_df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
                else:
                    best_df = pd.read_excel(path, sheet_name=sheet_name, header=header_row, engine="openpyxl")

        if best_df is None or best_score < minimum_score:
            raise ShopeeImportError("Não encontrei as colunas esperadas nesse relatório da Shopee.")

        best_df = best_df.dropna(how="all")
        best_df.columns = [str(col).strip() for col in best_df.columns]
        return best_df

    def _detect_header_row(self, raw: pd.DataFrame, rules: dict[str, tuple[str, ...]]) -> tuple[int | None, int]:
        max_rows = min(len(raw), 40)
        best_row: int | None = None
        best_score = -1

        for idx in range(max_rows):
            values = [normalize_text(value) for value in raw.iloc[idx].tolist()]
            joined = " | ".join(values)
            score = 0
            for candidates in rules.values():
                if any(normalize_text(candidate) in joined for candidate in candidates):
                    score += 1
            if score > best_score:
                best_row = idx
                best_score = score

        return best_row, best_score

    def _map_columns(self, columns: Any, rules: dict[str, tuple[str, ...]]) -> dict[str, str]:
        normalized_columns = [(normalize_text(col), str(col)) for col in columns]
        mapping: dict[str, str] = {}

        for target, candidates in rules.items():
            normalized_candidates = [normalize_text(candidate) for candidate in candidates]
            for candidate in normalized_candidates:
                for normalized, original in normalized_columns:
                    if normalized == candidate or candidate in normalized:
                        mapping[target] = original
                        break
                if target in mapping:
                    break
        return mapping

    def _require(self, mapping: dict[str, str], fields: list[str]) -> None:
        missing = [field for field in fields if field not in mapping]
        if missing:
            raise ShopeeImportError("Colunas obrigatórias não encontradas: " + ", ".join(missing))

    def _get(self, row: pd.Series, mapping: dict[str, str], field: str) -> str:
        column = mapping.get(field)
        if not column:
            return ""
        value = row.get(column, "")
        if pd.isna(value):
            return ""
        return str(value).strip()

    def _to_iso_datetime(self, value: object) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "nat", "-", "--"}:
            return ""
        try:
            parsed = pd.to_datetime(text, errors="coerce")
        except Exception:
            return text
        if pd.isna(parsed):
            return text

        dt = parsed.to_pydatetime()
        if isinstance(dt, datetime):
            return dt.isoformat(timespec="seconds")
        return str(dt)

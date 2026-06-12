from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils import int_to_safe, money_to_float, normalize_text


@dataclass
class ImportedLine:
    id_item_shopee: str
    produto_nome: str
    id_variacao_shopee: str
    variacao_nome: str
    sku_variacao: str
    vendas_pedido_pago: float
    unidades_pedido_pago: int
    tipo_linha: str
    contabilizar: bool


class ShopeeImportError(Exception):
    pass


class ShopeeImporter:
    """Leitor tolerante para relatórios de desempenho da Shopee."""

    SHEET_HINTS = ("produtos com melhor desempenho", "melhor desempenho", "produtos")

    COLUMN_RULES = {
        "id_item_shopee": ("id do item", "id item", "id do produto", "item id", "product id"),
        "produto_nome": ("produto", "nome do produto", "product name"),
        "id_variacao_shopee": ("id da variacao", "id de variacao", "id variacao", "variation id"),
        # Importante: não usar a regra genérica "variacao" aqui.
        # Ela faz a coluna "ID da Variação" ser confundida com "Nome da Variação".
        "variacao_nome": (
            "nome da variacao",
            "nome variacao",
            "variation name",
            "variation option",
            "opcao da variacao",
        ),
        "sku_variacao": ("sku da variacao", "sku variacao", "variation sku", "sku"),
        "vendas_pedido_pago": ("vendas (pedido pago)", "vendas pedido pago", "sales paid", "pedido pago", "vendas"),
        "unidades_pedido_pago": ("unidades (pedido pago)", "unidades pedido pago", "units paid", "quantidade", "unidades"),
    }

    def preview(self, file_path: str | Path) -> list[ImportedLine]:
        path = Path(file_path)
        if not path.exists():
            raise ShopeeImportError(f"Arquivo não encontrado: {path}")

        sheet_name = self._find_sheet(path)
        df = self._read_sheet_with_detected_header(path, sheet_name)
        if df.empty:
            raise ShopeeImportError("A planilha não possui dados úteis para importar.")

        column_map = self._map_columns(df.columns)
        self._validate_minimum_columns(column_map)

        imported: list[ImportedLine] = []
        for _, row in df.iterrows():
            product_name = self._get(row, column_map, "produto_nome")
            if not product_name or normalize_text(product_name) in {"nan", "none"}:
                continue

            variation_id = self._get(row, column_map, "id_variacao_shopee")
            variation_name = self._get(row, column_map, "variacao_nome")
            sku = self._get(row, column_map, "sku_variacao")
            revenue = money_to_float(self._get(row, column_map, "vendas_pedido_pago"))
            units = int_to_safe(self._get(row, column_map, "unidades_pedido_pago"))

            is_variation = self._is_real_variation(variation_id, variation_name, sku)
            should_count = is_variation and units > 0 and revenue > 0

            imported.append(
                ImportedLine(
                    id_item_shopee=self._get(row, column_map, "id_item_shopee"),
                    produto_nome=product_name,
                    id_variacao_shopee=variation_id,
                    variacao_nome=variation_name or "Sem variação",
                    sku_variacao=sku,
                    vendas_pedido_pago=revenue,
                    unidades_pedido_pago=units,
                    tipo_linha="variacao" if is_variation else "produto_pai",
                    contabilizar=should_count,
                )
            )

        if not imported:
            raise ShopeeImportError("Nenhuma linha de produto foi encontrada.")
        return imported

    def _find_sheet(self, path: Path) -> str:
        try:
            excel = pd.ExcelFile(path, engine="openpyxl")
        except Exception as exc:
            raise ShopeeImportError(f"Não consegui abrir a planilha: {exc}") from exc

        for name in excel.sheet_names:
            normalized = normalize_text(name)
            if any(hint in normalized for hint in self.SHEET_HINTS):
                return name
        return excel.sheet_names[0]

    def _read_sheet_with_detected_header(self, path: Path, sheet_name: str) -> pd.DataFrame:
        raw = pd.read_excel(path, sheet_name=sheet_name, header=None, engine="openpyxl")
        header_row = self._detect_header_row(raw)
        if header_row is None:
            df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
        else:
            df = pd.read_excel(path, sheet_name=sheet_name, header=header_row, engine="openpyxl")

        df = df.dropna(how="all")
        df.columns = [str(col).strip() for col in df.columns]
        return df

    def _detect_header_row(self, raw: pd.DataFrame) -> int | None:
        max_rows = min(len(raw), 20)
        for idx in range(max_rows):
            values = [normalize_text(value) for value in raw.iloc[idx].tolist()]
            joined = " | ".join(values)
            score = 0
            for candidates in self.COLUMN_RULES.values():
                if any(candidate in joined for candidate in candidates):
                    score += 1
            if score >= 3:
                return idx
        return None

    def _map_columns(self, columns: Any) -> dict[str, str]:
        normalized_columns = [(normalize_text(col), str(col)) for col in columns]
        mapping: dict[str, str] = {}

        for target, candidates in self.COLUMN_RULES.items():
            exact = self._find_exact_column(normalized_columns, candidates)
            if exact:
                mapping[target] = exact
                continue

            partial = self._find_partial_column(normalized_columns, candidates)
            if partial:
                mapping[target] = partial

        return mapping

    def _find_exact_column(self, normalized_columns: list[tuple[str, str]], candidates: tuple[str, ...]) -> str | None:
        normalized_candidates = [normalize_text(candidate) for candidate in candidates]
        for candidate in normalized_candidates:
            for normalized, original in normalized_columns:
                if normalized == candidate:
                    return original
        return None

    def _find_partial_column(self, normalized_columns: list[tuple[str, str]], candidates: tuple[str, ...]) -> str | None:
        normalized_candidates = [normalize_text(candidate) for candidate in candidates]
        for candidate in normalized_candidates:
            for normalized, original in normalized_columns:
                if candidate in normalized:
                    return original
        return None

    def _validate_minimum_columns(self, mapping: dict[str, str]) -> None:
        required = ["produto_nome", "vendas_pedido_pago", "unidades_pedido_pago"]
        missing = [field for field in required if field not in mapping]
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

    def _is_real_variation(self, variation_id: str, variation_name: str, sku: str) -> bool:
        values = [variation_id, variation_name, sku]
        for value in values:
            normalized = normalize_text(value)
            if normalized and normalized not in {"-", "--", "nan", "none", "sem variacao"}:
                return True
        return False

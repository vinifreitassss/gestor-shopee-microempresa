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
    """Leitor tolerante para relatórios de desempenho da Shopee.

    A central de importações também recebe relatórios do Mercado Livre.
    Quando o arquivo é identificado como ML, o leitor delega ao importador
    específico do ML e devolve o mesmo formato interno esperado pela UI.

    Regra importante:
    - Produtos com variações: contabiliza somente linhas de variação, para não duplicar o pai.
    - Produtos sem variações: contabiliza a própria linha pai como "Sem variação".
    """

    SHEET_HINTS = ("produtos com melhor desempenho", "melhor desempenho", "produtos")

    COLUMN_RULES = {
        "id_item_shopee": ("id do item", "id item", "id do produto", "item id", "product id"),
        "produto_nome": ("produto", "nome do produto", "product name"),
        "id_variacao_shopee": ("id da variacao", "id de variacao", "id variacao", "variation id"),
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

    @staticmethod
    def _looks_like_mercadolivre(path: Path) -> bool:
        """Identifica ML pelo nome do arquivo e, como fallback, pelo cabeçalho."""
        name = normalize_text(path.name)
        if any(token in name for token in ("mercado livre", "mercadolivre", "mercado_livre", "ml_", "ml-")):
            return True
        try:
            raw = pd.read_excel(path, sheet_name=0, header=None, nrows=20, engine="openpyxl")
            text = " ".join(normalize_text(v) for v in raw.fillna("").astype(str).values.flatten())
            ml_markers = ("anuncio", "unidades vendidas", "vendas brutas", "relatorio de desempenho")
            return sum(marker in text for marker in ml_markers) >= 2
        except Exception:
            return False

    def preview(self, file_path: str | Path) -> list[ImportedLine]:
        path = Path(file_path)
        if not path.exists():
            raise ShopeeImportError(f"Arquivo não encontrado: {path}")

        if self._looks_like_mercadolivre(path):
            try:
                from src.services.mercadolivre_import_service import preview_mercadolivre

                preview = preview_mercadolivre(str(path))
                imported = []
                for row in preview["rows"]:
                    imported.append(
                        ImportedLine(
                            id_item_shopee=str(row.get("ad_id") or ""),
                            produto_nome=str(row.get("produto_nome") or ""),
                            id_variacao_shopee=str(row.get("ad_id") or ""),
                            variacao_nome=str(row.get("variacao_nome") or "Sem variação"),
                            sku_variacao=str(row.get("sku") or ""),
                            vendas_pedido_pago=float(row.get("faturamento") or 0),
                            unidades_pedido_pago=int(row.get("unidades") or 0),
                            tipo_linha="mercadolivre",
                            contabilizar=True,
                        )
                    )
                if not imported:
                    raise ShopeeImportError("Nenhuma venda do Mercado Livre foi encontrada.")
                return imported
            except ValueError as exc:
                raise ShopeeImportError(str(exc)) from exc
            except Exception as exc:
                if isinstance(exc, ShopeeImportError):
                    raise
                raise ShopeeImportError(f"Não consegui ler o relatório do Mercado Livre: {exc}") from exc

        sheet_name = self._find_sheet(path)
        df = self._read_sheet_with_detected_header(path, sheet_name)
        if df.empty:
            raise ShopeeImportError("A planilha não possui dados úteis para importar.")

        column_map = self._map_columns(df.columns)
        self._validate_minimum_columns(column_map)

        raw_lines: list[dict] = []
        product_keys_with_variation: set[str] = set()

        for _, row in df.iterrows():
            product_name = self._get(row, column_map, "produto_nome")
            if not product_name or normalize_text(product_name) in {"nan", "none"}:
                continue

            item_id = self._get(row, column_map, "id_item_shopee")
            variation_id = self._get(row, column_map, "id_variacao_shopee")
            variation_name = self._get(row, column_map, "variacao_nome")
            sku = self._get(row, column_map, "sku_variacao")
            revenue = money_to_float(self._get(row, column_map, "vendas_pedido_pago"))
            units = int_to_safe(self._get(row, column_map, "unidades_pedido_pago"))

            is_variation = self._is_real_variation(variation_id, variation_name, sku)
            product_key = self._product_key(item_id, product_name)
            if is_variation:
                product_keys_with_variation.add(product_key)

            raw_lines.append(
                {
                    "item_id": item_id,
                    "product_name": product_name,
                    "variation_id": variation_id,
                    "variation_name": variation_name,
                    "sku": sku,
                    "revenue": revenue,
                    "units": units,
                    "is_variation": is_variation,
                    "product_key": product_key,
                }
            )

        imported: list[ImportedLine] = []
        for line in raw_lines:
            is_variation = bool(line["is_variation"])
            has_variation_children = str(line["product_key"]) in product_keys_with_variation
            units = int(line["units"] or 0)
            revenue = float(line["revenue"] or 0)

            if is_variation:
                tipo_linha = "variacao"
                variation_name = str(line["variation_name"] or "Sem variação")
                should_count = units > 0 and revenue > 0
            elif not has_variation_children:
                tipo_linha = "produto_sem_variacao"
                variation_name = "Sem variação"
                should_count = units > 0 and revenue > 0
            else:
                tipo_linha = "produto_pai"
                variation_name = str(line["variation_name"] or "Sem variação")
                should_count = False

            imported.append(
                ImportedLine(
                    id_item_shopee=str(line["item_id"] or ""),
                    produto_nome=str(line["product_name"]),
                    id_variacao_shopee=str(line["variation_id"] or ""),
                    variacao_nome=variation_name,
                    sku_variacao=str(line["sku"] or ""),
                    vendas_pedido_pago=revenue,
                    unidades_pedido_pago=units,
                    tipo_linha=tipo_linha,
                    contabilizar=should_count,
                )
            )

        if not imported:
            raise ShopeeImportError("Nenhuma linha de produto foi encontrada.")
        return imported

    def _product_key(self, item_id: str, product_name: str) -> str:
        normalized_id = normalize_text(item_id)
        if normalized_id and normalized_id not in {"-", "--", "nan", "none"}:
            return f"id:{normalized_id}"
        return f"nome:{normalize_text(product_name)}"

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

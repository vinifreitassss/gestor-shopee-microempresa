from datetime import date
from pathlib import Path
import re
import unicodedata

from openpyxl import load_workbook

from src.calculators import calculate_sale_profit
from src.database import fetch_all, get_connection, now_iso
from src.services.settings_service import get_setting_float
from src.utils import mes_referencia_from_date

REPORT_TYPE = "mercadolivre_performance"


def _norm(value) -> str:
    return "" if value is None else str(value).strip()


def _key(value) -> str:
    text = unicodedata.normalize("NFKD", _norm(value).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text)


def _money(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _norm(value).replace("R$", "").replace(" ", "")
    if not text:
        return 0.0
    # Aceita tanto "482,50" quanto "1.234,56" e valores numéricos exportados pelo Excel.
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(".", "") if text.count(".") > 1 else text
    try:
        return float(text)
    except ValueError:
        return 0.0


def _int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


# Colunas do relatório padrão informado pelo usuário.
# Não usamos "Quantidade de vendas" como unidades: no ML ela representa pedidos,
# enquanto "Unidades vendidas" representa a quantidade real de peças.
COLUMN_ALIASES = {
    "ad_id": ["ID do anúncio", "ID do anuncio", "ID anúncio", "ID anuncio", "Anúncio ID", "Anuncio ID"],
    "produto_nome": ["Anúncio", "Anuncio", "Título", "Titulo", "Produto", "Nome do anúncio", "Nome do anuncio"],
    "variacao_nome": ["Variação", "Variacao", "Variação do anúncio", "Variacao do anuncio"],
    "sku": ["SKU", "SKU da variação", "SKU da variacao"],
    "status": ["Status atual", "Status"],
    "unidades": ["Unidades vendidas", "Unidades", "Quantidade vendida", "Itens vendidos"],
    "faturamento": ["Vendas brutas (BRL)", "Vendas brutas (R$)", "Vendas brutas", "Valor vendido", "Faturamento", "Receita bruta", "Total vendido"],
}


def _find_col(headers: list[str], aliases: list[str]) -> int | None:
    normalized = [_key(header) for header in headers]
    for alias in aliases:
        key = _key(alias)
        if key in normalized:
            return normalized.index(key)
    for alias in aliases:
        key = _key(alias)
        if not key:
            continue
        for i, header in enumerate(normalized):
            if key in header or header in key:
                return i
    return None


def _find_header_and_columns(ws):
    best = None
    for row_number, raw in enumerate(ws.iter_rows(min_row=1, max_row=60, values_only=True), 1):
        headers = [_norm(v) for v in raw]
        cols = {field: _find_col(headers, aliases) for field, aliases in COLUMN_ALIASES.items()}
        score = sum(cols[field] is not None for field in ("ad_id", "produto_nome", "unidades", "faturamento"))
        if best is None or score > best[0]:
            best = (score, row_number, headers, cols)
        # O cabeçalho padrão fornecido tem ID, Anúncio, Unidades vendidas e Vendas brutas.
        if score == 4:
            return row_number, headers, cols
    raise ValueError(
        "Não consegui identificar o cabeçalho do Mercado Livre. "
        "A planilha esperada precisa conter pelo menos: ID do anúncio, Anúncio, Unidades vendidas e Vendas brutas (BRL)."
    )


def _report_period(ws) -> tuple[date, date]:
    text = ""
    for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
        text += " " + " ".join(_norm(v) for v in row if v is not None)
    match = re.search(
        r"de\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})\s+até\s+(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
        text,
        re.I,
    )
    months = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    }
    if not match:
        raise ValueError("Não consegui identificar o período do relatório no texto da planilha.")
    try:
        start = date(int(match.group(3)), months[match.group(2).lower()], int(match.group(1)))
        end = date(int(match.group(6)), months[match.group(5).lower()], int(match.group(4)))
    except (KeyError, ValueError) as exc:
        raise ValueError("O período informado no relatório do Mercado Livre é inválido.") from exc
    if end < start:
        raise ValueError("O período final do relatório do Mercado Livre é anterior ao inicial.")
    return start, end


def preview_mercadolivre(file_path: str) -> dict:
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"Arquivo não encontrado: {path}")
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("O relatório do Mercado Livre deve ser um arquivo Excel .xlsx ou .xlsm.")

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        # O relatório padrão costuma vir em "Relatório". Se o nome mudar,
        # usamos a primeira aba, mas nunca inventamos uma estrutura diferente.
        ws = wb["Relatório"] if "Relatório" in wb.sheetnames else wb.active
        header_row, headers, cols = _find_header_and_columns(ws)
        start, end = _report_period(ws)
        rows = []
        seen_ad_ids = set()

        for raw_values in ws.iter_rows(min_row=header_row + 1, values_only=True):
            values = list(raw_values)
            if len(values) < len(headers):
                values.extend([None] * (len(headers) - len(values)))

            name = _norm(values[cols["produto_nome"]])
            units = _int(values[cols["unidades"]])
            gross = _money(values[cols["faturamento"]])
            if not name or units <= 0 or gross <= 0:
                continue

            ad_id = _norm(values[cols["ad_id"]])
            if not ad_id:
                raise ValueError(f"O anúncio '{name}' possui vendas, mas está sem ID do anúncio.")

            # Cada ID de anúncio é uma unidade comercial do ML. Não agrupamos anúncios
            # diferentes apenas pelo nome, pois anúncios iguais podem ter preços/condições diferentes.
            variation = _norm(values[cols["variacao_nome"]]) if cols["variacao_nome"] is not None else ""
            sku = _norm(values[cols["sku"]]) if cols["sku"] is not None else ""
            status = _norm(values[cols["status"]]) if cols["status"] is not None else ""

            key = (ad_id, variation or "Sem variação", sku)
            if key in seen_ad_ids:
                raise ValueError(
                    f"O relatório contém mais de uma linha de venda para o anúncio {ad_id} "
                    "com a mesma identificação. A importação foi interrompida para evitar duplicidade."
                )
            seen_ad_ids.add(key)
            rows.append({
                "ad_id": ad_id,
                "produto_nome": name,
                "variacao_nome": variation or "Sem variação",
                "sku": sku,
                "status": status,
                "unidades": units,
                "faturamento": gross,
            })

        return {
            "arquivo": path.name,
            "data_inicio": start,
            "data_fim": end,
            "rows": rows,
            "count": len(rows),
            "faturamento": sum(r["faturamento"] for r in rows),
            "unidades": sum(r["unidades"] for r in rows),
        }
    finally:
        wb.close()


def _upsert_ml_product(conn, row: dict) -> tuple[int, int]:
    # Prefixo ML impede que IDs do ML colidam com IDs internos da Shopee.
    parent_key = f"ML:{row['ad_id']}"
    existing = conn.execute("SELECT id FROM produtos_pai WHERE id_item_shopee = ?", (parent_key,)).fetchone()
    if existing:
        parent_id = int(existing["id"])
        conn.execute("UPDATE produtos_pai SET nome = ?, ativo = 1 WHERE id = ?", (row["produto_nome"], parent_id))
    else:
        cur = conn.execute(
            "INSERT INTO produtos_pai (id_item_shopee, nome, ativo, criado_em) VALUES (?, ?, 1, ?)",
            (parent_key, row["produto_nome"], now_iso()),
        )
        parent_id = int(cur.lastrowid)

    variation_key = f"ML:{row['ad_id']}:{row['variacao_nome']}"
    existing = conn.execute("SELECT id FROM variacoes WHERE id_variacao_shopee = ?", (variation_key,)).fetchone()
    sku = row["sku"] or f"ML:{row['ad_id']}"
    if existing:
        variation_id = int(existing["id"])
        conn.execute(
            "UPDATE variacoes SET produto_pai_id = ?, nome_variacao = ?, sku = ?, ativo = 1 WHERE id = ?",
            (parent_id, row["variacao_nome"], sku, variation_id),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO variacoes (produto_pai_id, id_variacao_shopee, nome_variacao, sku, tipo_produto, ativo, criado_em)
            VALUES (?, ?, ?, ?, 'pronto', 1, ?)
            """,
            (parent_id, variation_key, row["variacao_nome"], sku, now_iso()),
        )
        variation_id = int(cur.lastrowid)
    return parent_id, variation_id


def _current_cost(conn, variation_id: int) -> float | None:
    row = conn.execute(
        "SELECT custo_unitario FROM custos_variacao WHERE variacao_id = ? AND ativo = 1 ORDER BY criado_em DESC, id DESC LIMIT 1",
        (variation_id,),
    ).fetchone()
    return float(row["custo_unitario"]) if row else None


def find_ml_importations_same_period(data_inicio: date, data_fim: date) -> list[dict]:
    return fetch_all(
        """
        SELECT id, arquivo_nome, data_inicio, data_fim, mes_referencia, criado_em
        FROM importacoes
        WHERE tipo_relatorio = ? AND data_inicio = ? AND data_fim = ? AND status = 'confirmada'
        ORDER BY criado_em DESC
        """,
        (REPORT_TYPE, data_inicio.isoformat(), data_fim.isoformat()),
    )


def save_mercadolivre_importation(file_path: str, data_inicio: date | None = None, data_fim: date | None = None, replace_same_period: bool = True) -> dict:
    preview = preview_mercadolivre(file_path)
    # O período oficial é o que veio no relatório, evitando que uma edição manual
    # na tela faça uma venda ser lançada no mês errado.
    report_start = preview["data_inicio"]
    report_end = preview["data_fim"]
    if data_inicio is not None and data_inicio != report_start:
        raise ValueError("A data inicial informada na tela não coincide com a data do relatório ML.")
    if data_fim is not None and data_fim != report_end:
        raise ValueError("A data final informada na tela não coincide com a data do relatório ML.")

    data_inicio = report_start
    data_fim = report_end
    ml_tax = get_setting_float("ml_imposto_percentual", 9)
    ml_commission = get_setting_float("ml_comissao_percentual", 22)
    ml_fixed_fee = get_setting_float("ml_taxa_fixa_unidade", 8)

    with get_connection() as conn:
        if replace_same_period:
            existing = conn.execute(
                "SELECT id FROM importacoes WHERE tipo_relatorio = ? AND data_inicio = ? AND data_fim = ? AND status = 'confirmada'",
                (REPORT_TYPE, data_inicio.isoformat(), data_fim.isoformat()),
            ).fetchall()
            for row in existing:
                conn.execute("DELETE FROM importacoes WHERE id = ?", (row["id"],))

        cur = conn.execute(
            """
            INSERT INTO importacoes (arquivo_nome, caminho_arquivo, tipo_relatorio, tipo_periodo, data_inicio, data_fim, mes_referencia, status, criado_em)
            VALUES (?, ?, ?, 'personalizado', ?, ?, ?, 'confirmada', ?)
            """,
            (
                Path(file_path).name,
                str(Path(file_path)),
                REPORT_TYPE,
                data_inicio.isoformat(),
                data_fim.isoformat(),
                mes_referencia_from_date(data_inicio),
                now_iso(),
            ),
        )
        importacao_id = int(cur.lastrowid)
        inserted = 0
        incomplete = 0

        for row in preview["rows"]:
            parent_id, variation_id = _upsert_ml_product(conn, row)
            cost = _current_cost(conn, variation_id)
            calc = calculate_sale_profit(
                row["faturamento"],
                row["unidades"],
                ml_tax,
                ml_commission,
                ml_fixed_fee,
                cost,
            )
            incomplete += 1 if calc.lucro_incompleto else 0
            conn.execute(
                """
                INSERT INTO vendas_contabilizadas (
                    importacao_id, produto_pai_id, variacao_id, data_inicio, data_fim, mes_referencia,
                    unidades, faturamento, imposto_percentual, comissao_percentual, taxa_fixa_unitaria,
                    imposto_valor, comissao_valor, taxa_fixa_valor, custo_unitario_usado, custo_total,
                    lucro, lucro_incompleto, criado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    importacao_id,
                    parent_id,
                    variation_id,
                    data_inicio.isoformat(),
                    data_fim.isoformat(),
                    mes_referencia_from_date(data_inicio),
                    calc.unidades,
                    calc.faturamento,
                    calc.imposto_percentual,
                    calc.comissao_percentual,
                    calc.taxa_fixa_unitaria,
                    calc.imposto_valor,
                    calc.comissao_valor,
                    calc.taxa_fixa_valor,
                    calc.custo_unitario,
                    calc.custo_total,
                    calc.lucro,
                    1 if calc.lucro_incompleto else 0,
                    now_iso(),
                ),
            )
            inserted += 1

    return {
        "importacao_id": importacao_id,
        "inserted": inserted,
        "incomplete": incomplete,
        "faturamento": preview["faturamento"],
        "unidades": preview["unidades"],
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "imposto_percentual": ml_tax,
        "comissao_percentual": ml_commission,
        "taxa_fixa_unidade": ml_fixed_fee,
    }

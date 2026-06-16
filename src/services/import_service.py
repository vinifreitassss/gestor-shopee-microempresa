from datetime import date
from pathlib import Path

from src.calculators import calculate_sale_profit
from src.database import fetch_all, get_connection, now_iso
from src.importer import ImportedLine, ShopeeImporter
from src.services.settings_service import get_setting_float
from src.utils import mes_referencia_from_date


def save_importation(
    file_path: str,
    tipo_periodo: str,
    data_inicio: date,
    data_fim: date,
    mode: str = "perguntar",
) -> int:
    """Importa e salva a planilha de desempenho/vendas da Shopee.

    mode aceita:
    - substituir: apaga importações confirmadas no mesmo período antes de salvar;
    - substituir_mes: apaga importações mensais confirmadas do mesmo mês antes de salvar;
    - somar: mantém o que existe e adiciona nova importação.
    """
    path = Path(file_path)
    mes_ref = mes_referencia_from_date(data_inicio)
    importer = ShopeeImporter()
    lines = importer.preview(path)

    with get_connection() as conn:
        if mode == "substituir_mes":
            existing = conn.execute(
                """
                SELECT id FROM importacoes
                WHERE tipo_relatorio = 'performance'
                  AND tipo_periodo = ?
                  AND mes_referencia = ?
                  AND status = 'confirmada'
                """,
                (tipo_periodo, mes_ref),
            ).fetchall()
            for row in existing:
                conn.execute("DELETE FROM importacoes WHERE id = ?", (row["id"],))

        elif mode == "substituir":
            existing = conn.execute(
                """
                SELECT id FROM importacoes
                WHERE tipo_relatorio = 'performance'
                  AND tipo_periodo = ?
                  AND data_inicio = ?
                  AND data_fim = ?
                  AND status = 'confirmada'
                """,
                (tipo_periodo, data_inicio.isoformat(), data_fim.isoformat()),
            ).fetchall()
            for row in existing:
                conn.execute("DELETE FROM importacoes WHERE id = ?", (row["id"],))

        cursor = conn.execute(
            """
            INSERT INTO importacoes (
                arquivo_nome, caminho_arquivo, tipo_relatorio, tipo_periodo, data_inicio, data_fim,
                mes_referencia, status, criado_em
            ) VALUES (?, ?, 'performance', ?, ?, ?, ?, 'confirmada', ?)
            """,
            (
                path.name,
                str(path),
                tipo_periodo,
                data_inicio.isoformat(),
                data_fim.isoformat(),
                mes_ref,
                now_iso(),
            ),
        )
        importacao_id = int(cursor.lastrowid)

        for line in lines:
            conn.execute(
                """
                INSERT INTO linhas_importadas (
                    importacao_id, id_item_shopee, produto_nome, id_variacao_shopee,
                    variacao_nome, sku_variacao, vendas_pedido_pago, unidades_pedido_pago,
                    tipo_linha, contabilizar
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    importacao_id,
                    line.id_item_shopee,
                    line.produto_nome,
                    line.id_variacao_shopee,
                    line.variacao_nome,
                    line.sku_variacao,
                    line.vendas_pedido_pago,
                    line.unidades_pedido_pago,
                    line.tipo_linha,
                    1 if line.contabilizar else 0,
                ),
            )

        _upsert_products_and_sales(conn, importacao_id, lines, data_inicio, data_fim, mes_ref)

    return importacao_id


def list_importations() -> list[dict]:
    return fetch_all(
        """
        SELECT
            id,
            arquivo_nome,
            tipo_relatorio,
            tipo_periodo,
            data_inicio,
            data_fim,
            mes_referencia,
            status,
            criado_em
        FROM importacoes
        ORDER BY criado_em DESC
        LIMIT 100
        """
    )


def get_importation(importacao_id: int) -> dict | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                id,
                arquivo_nome,
                tipo_relatorio,
                tipo_periodo,
                data_inicio,
                data_fim,
                mes_referencia,
                status,
                criado_em,
                (
                    SELECT COUNT(*)
                    FROM vendas_contabilizadas v
                    WHERE v.importacao_id = importacoes.id
                ) AS vendas_contabilizadas
            FROM importacoes
            WHERE id = ?
            """,
            (importacao_id,),
        ).fetchone()


def delete_importation(importacao_id: int) -> bool:
    """Exclui uma planilha importada e os dados gerados por ela."""
    with get_connection() as conn:
        current = conn.execute(
            "SELECT id, tipo_relatorio FROM importacoes WHERE id = ?",
            (importacao_id,),
        ).fetchone()
        if not current:
            return False

        report_type = current["tipo_relatorio"]

        if report_type == "performance":
            conn.execute("DELETE FROM importacoes WHERE id = ?", (importacao_id,))
            return True

        if report_type == "pedidos_enviados":
            conn.execute("DELETE FROM shopee_itens_pedido WHERE importacao_id = ?", (importacao_id,))
            conn.execute("DELETE FROM shopee_pedidos_financeiros WHERE importacao_id = ?", (importacao_id,))
            conn.execute("DELETE FROM importacoes WHERE id = ?", (importacao_id,))
            from src.services.financial_import_service import _reconcile_all_orders

            _reconcile_all_orders(conn)
            return True

        if report_type == "pagamentos_shopee":
            conn.execute("DELETE FROM shopee_saques WHERE importacao_id = ?", (importacao_id,))
            conn.execute("DELETE FROM shopee_transacoes WHERE importacao_id = ?", (importacao_id,))
            conn.execute("DELETE FROM importacoes WHERE id = ?", (importacao_id,))
            from src.services.financial_import_service import _reconcile_all_orders

            _reconcile_all_orders(conn)
            return True

        conn.execute("DELETE FROM importacoes WHERE id = ?", (importacao_id,))
        return True


def _upsert_products_and_sales(conn, importacao_id: int, lines: list[ImportedLine], data_inicio: date, data_fim: date, mes_ref: str) -> None:
    imposto = get_setting_float("imposto_percentual", 9)
    comissao = get_setting_float("comissao_percentual", 22)
    taxa = get_setting_float("taxa_fixa_unidade", 5)

    for line in lines:
        if not line.contabilizar:
            continue

        produto_pai_id = _upsert_parent_product(conn, line.id_item_shopee, line.produto_nome)
        variacao_id = _upsert_variation(
            conn,
            produto_pai_id,
            line.id_variacao_shopee,
            line.variacao_nome,
            line.sku_variacao,
        )
        custo_unitario = _get_current_cost(conn, variacao_id)
        calc = calculate_sale_profit(
            faturamento=line.vendas_pedido_pago,
            unidades=line.unidades_pedido_pago,
            imposto_percentual=imposto,
            comissao_percentual=comissao,
            taxa_fixa_unitaria=taxa,
            custo_unitario=custo_unitario,
        )

        conn.execute(
            """
            INSERT INTO vendas_contabilizadas (
                importacao_id, produto_pai_id, variacao_id, data_inicio, data_fim,
                mes_referencia, unidades, faturamento, imposto_percentual,
                comissao_percentual, taxa_fixa_unitaria, imposto_valor, comissao_valor,
                taxa_fixa_valor, custo_unitario_usado, custo_total, lucro,
                lucro_incompleto, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                importacao_id,
                produto_pai_id,
                variacao_id,
                data_inicio.isoformat(),
                data_fim.isoformat(),
                mes_ref,
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


def _upsert_parent_product(conn, id_item_shopee: str, name: str) -> int:
    existing = None
    if id_item_shopee:
        existing = conn.execute(
            "SELECT id FROM produtos_pai WHERE id_item_shopee = ?",
            (id_item_shopee,),
        ).fetchone()
    if existing:
        conn.execute(
            "UPDATE produtos_pai SET nome = ? WHERE id = ?",
            (name, existing["id"]),
        )
        return int(existing["id"])

    cursor = conn.execute(
        """
        INSERT INTO produtos_pai (id_item_shopee, nome, ativo, criado_em)
        VALUES (?, ?, 1, ?)
        """,
        (id_item_shopee or None, name, now_iso()),
    )
    return int(cursor.lastrowid)


def _upsert_variation(conn, produto_pai_id: int, variation_id: str, variation_name: str, sku: str) -> int:
    existing = None
    if variation_id:
        existing = conn.execute(
            "SELECT id FROM variacoes WHERE id_variacao_shopee = ?",
            (variation_id,),
        ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE variacoes
            SET produto_pai_id = ?,
                nome_variacao = ?,
                sku = COALESCE(NULLIF(?, ''), sku)
            WHERE id = ?
            """,
            (produto_pai_id, variation_name or "Sem variação", sku or "", existing["id"]),
        )
        return int(existing["id"])

    cursor = conn.execute(
        """
        INSERT INTO variacoes (
            produto_pai_id, id_variacao_shopee, nome_variacao, sku,
            tipo_produto, ativo, criado_em
        ) VALUES (?, ?, ?, ?, 'pronto', 1, ?)
        """,
        (produto_pai_id, variation_id or None, variation_name or "Sem variação", sku or None, now_iso()),
    )
    return int(cursor.lastrowid)


def _get_current_cost(conn, variacao_id: int) -> float | None:
    row = conn.execute(
        """
        SELECT custo_unitario
        FROM custos_variacao
        WHERE variacao_id = ? AND ativo = 1
        ORDER BY criado_em DESC, id DESC
        LIMIT 1
        """,
        (variacao_id,),
    ).fetchone()
    if not row:
        return None
    return float(row["custo_unitario"])


def find_importations_same_period(tipo_periodo: str, data_inicio: date, data_fim: date) -> list[dict]:
    return fetch_all(
        """
        SELECT * FROM importacoes
        WHERE tipo_relatorio = 'performance'
          AND tipo_periodo = ?
          AND data_inicio = ?
          AND data_fim = ?
          AND status = 'confirmada'
        ORDER BY criado_em DESC
        """,
        (tipo_periodo, data_inicio.isoformat(), data_fim.isoformat()),
    )


def find_importations_same_month(report_type: str, tipo_periodo: str, mes_referencia: str) -> list[dict]:
    return fetch_all(
        """
        SELECT * FROM importacoes
        WHERE tipo_relatorio = ?
          AND tipo_periodo = ?
          AND mes_referencia = ?
          AND status = 'confirmada'
        ORDER BY criado_em DESC
        """,
        (report_type, tipo_periodo, mes_referencia),
    )

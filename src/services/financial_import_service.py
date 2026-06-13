from datetime import date
from pathlib import Path
import sqlite3

from src.database import fetch_all, get_connection, now_iso
from src.importers.shopee_financial_importer import (
    BalanceTransaction,
    FinancialOrder,
    ShopeeFinancialImporter,
)
from src.utils import mes_referencia_from_date, normalize_text


REPORT_TYPE_LABELS = {
    "pedidos_enviados": "Pedidos enviados / em espera",
    "pagamentos_shopee": "Pagamentos e saques Shopee",
}


def preview_financial_importation(file_path: str, report_type: str, data_envio_real: date | None = None) -> dict:
    importer = ShopeeFinancialImporter()

    if report_type == "pedidos_enviados":
        orders = importer.preview_orders(file_path, data_envio_real=data_envio_real)
        valor_total = sum(order.valor_total for order in orders)
        liquido = sum(order.valor_liquido_estimado for order in orders)
        taxas = sum(order.comissao_liquida + order.taxa_servico_liquida + order.taxa_transacao for order in orders)
        rows = [
            {
                "pedido_id": order.pedido_id,
                "status": order.status_pedido,
                "data": order.data_envio_real or order.data_prevista_envio,
                "valor": order.valor_total,
                "liquido": order.valor_liquido_estimado,
                "obs": f"{len(order.itens)} item(ns)",
            }
            for order in orders[:200]
        ]
        return {
            "report_type": report_type,
            "count": len(orders),
            "valor_total": valor_total,
            "valor_liquido": liquido,
            "taxas": taxas,
            "rows": rows,
        }

    if report_type == "pagamentos_shopee":
        transactions = importer.preview_transactions(file_path)
        entradas = sum(t.valor for t in transactions if normalize_text(t.direcao) == "entrada")
        saques = sum(abs(t.valor) for t in transactions if t.is_saque)
        pedidos = sum(1 for t in transactions if t.is_entrada_com_pedido)
        rows = [
            {
                "pedido_id": transaction.pedido_id,
                "status": transaction.tipo_transacao,
                "data": transaction.data_movimento,
                "valor": transaction.valor,
                "liquido": transaction.balanca_apos_transacoes,
                "obs": transaction.direcao,
            }
            for transaction in transactions[:200]
        ]
        return {
            "report_type": report_type,
            "count": len(transactions),
            "valor_total": entradas,
            "valor_liquido": entradas - saques,
            "taxas": saques,
            "pedidos": pedidos,
            "rows": rows,
        }

    raise ValueError(f"Tipo de relatório financeiro desconhecido: {report_type}")


def save_financial_importation(
    file_path: str,
    report_type: str,
    tipo_periodo: str,
    data_inicio: date,
    data_fim: date,
    mode: str = "perguntar",
) -> int:
    path = Path(file_path)
    mes_ref = mes_referencia_from_date(data_inicio)
    importer = ShopeeFinancialImporter()

    with get_connection() as conn:
        if mode == "substituir":
            _delete_existing_same_period(conn, report_type, tipo_periodo, data_inicio, data_fim)

        importacao_id = _create_importation(conn, path, report_type, tipo_periodo, data_inicio, data_fim, mes_ref)

        if report_type == "pedidos_enviados":
            orders = importer.preview_orders(path, data_envio_real=data_fim)
            _save_orders(conn, importacao_id, orders)
            _reconcile_all_orders(conn)
            return importacao_id

        if report_type == "pagamentos_shopee":
            transactions = importer.preview_transactions(path)
            _save_transactions(conn, importacao_id, transactions)
            _reconcile_all_orders(conn)
            return importacao_id

        raise ValueError(f"Tipo de relatório financeiro desconhecido: {report_type}")


def find_financial_importations_same_period(
    report_type: str,
    tipo_periodo: str,
    data_inicio: date,
    data_fim: date,
) -> list[dict]:
    return fetch_all(
        """
        SELECT * FROM importacoes
        WHERE tipo_relatorio = ?
          AND tipo_periodo = ?
          AND data_inicio = ?
          AND data_fim = ?
          AND status = 'confirmada'
        ORDER BY criado_em DESC
        """,
        (report_type, tipo_periodo, data_inicio.isoformat(), data_fim.isoformat()),
    )


def _create_importation(
    conn: sqlite3.Connection,
    path: Path,
    report_type: str,
    tipo_periodo: str,
    data_inicio: date,
    data_fim: date,
    mes_ref: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO importacoes (
            arquivo_nome, caminho_arquivo, tipo_relatorio, tipo_periodo, data_inicio, data_fim,
            mes_referencia, status, criado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'confirmada', ?)
        """,
        (
            path.name,
            str(path),
            report_type,
            tipo_periodo,
            data_inicio.isoformat(),
            data_fim.isoformat(),
            mes_ref,
            now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def _delete_existing_same_period(
    conn: sqlite3.Connection,
    report_type: str,
    tipo_periodo: str,
    data_inicio: date,
    data_fim: date,
) -> None:
    # Os dados financeiros são idempotentes por pedido/transação.
    # Mantemos o histórico de importações e evitamos apagar dados já conciliados.
    return


def _save_orders(conn: sqlite3.Connection, importacao_id: int, orders: list[FinancialOrder]) -> None:
    timestamp = now_iso()

    for order in orders:
        conn.execute(
            """
            INSERT INTO shopee_pedidos_financeiros (
                pedido_id, importacao_id, status_pedido, data_criacao, data_pagamento,
                data_prevista_envio, data_envio_real, valor_total, total_global, taxa_transacao,
                comissao_bruta, comissao_liquida, taxa_servico_bruta, taxa_servico_liquida,
                valor_liquido_estimado, status_financeiro, criado_em, atualizado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'em_espera', ?, ?)
            ON CONFLICT(pedido_id) DO UPDATE SET
                importacao_id = excluded.importacao_id,
                status_pedido = excluded.status_pedido,
                data_criacao = excluded.data_criacao,
                data_pagamento = excluded.data_pagamento,
                data_prevista_envio = excluded.data_prevista_envio,
                data_envio_real = excluded.data_envio_real,
                valor_total = excluded.valor_total,
                total_global = excluded.total_global,
                taxa_transacao = excluded.taxa_transacao,
                comissao_bruta = excluded.comissao_bruta,
                comissao_liquida = excluded.comissao_liquida,
                taxa_servico_bruta = excluded.taxa_servico_bruta,
                taxa_servico_liquida = excluded.taxa_servico_liquida,
                valor_liquido_estimado = excluded.valor_liquido_estimado,
                atualizado_em = excluded.atualizado_em
            """,
            (
                order.pedido_id,
                importacao_id,
                order.status_pedido,
                order.data_criacao,
                order.data_pagamento,
                order.data_prevista_envio,
                order.data_envio_real,
                order.valor_total,
                order.total_global,
                order.taxa_transacao,
                order.comissao_bruta,
                order.comissao_liquida,
                order.taxa_servico_bruta,
                order.taxa_servico_liquida,
                order.valor_liquido_estimado,
                timestamp,
                timestamp,
            ),
        )

        for item in order.itens:
            conn.execute(
                """
                INSERT INTO shopee_itens_pedido (
                    pedido_id, importacao_id, produto_nome, sku, variacao_nome,
                    quantidade, subtotal_produto, criado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.pedido_id,
                    importacao_id,
                    item.produto_nome,
                    item.sku,
                    item.variacao_nome,
                    item.quantidade,
                    item.subtotal_produto,
                    timestamp,
                ),
            )


def _save_transactions(
    conn: sqlite3.Connection,
    importacao_id: int,
    transactions: list[BalanceTransaction],
) -> None:
    timestamp = now_iso()

    for transaction in transactions:
        conn.execute(
            """
            INSERT OR IGNORE INTO shopee_transacoes (
                importacao_id, data_movimento, tipo_transacao, descricao, pedido_id, direcao,
                valor, status, balanca_apos_transacoes, valor_ajustado,
                status_conciliacao, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendente', ?)
            """,
            (
                importacao_id,
                transaction.data_movimento,
                transaction.tipo_transacao,
                transaction.descricao,
                transaction.pedido_id or None,
                transaction.direcao,
                transaction.valor,
                transaction.status,
                transaction.balanca_apos_transacoes,
                transaction.valor_ajustado,
                timestamp,
            ),
        )

        if transaction.is_saque:
            transaction_id = _find_transaction_id(conn, transaction)
            conn.execute(
                """
                INSERT OR IGNORE INTO shopee_saques (
                    transacao_id, importacao_id, data_saque, valor,
                    saldo_apos_transacao, status, criado_em
                ) VALUES (?, ?, ?, ?, ?, 'a_conciliar', ?)
                """,
                (
                    transaction_id,
                    importacao_id,
                    transaction.data_movimento,
                    abs(transaction.valor),
                    transaction.balanca_apos_transacoes,
                    timestamp,
                ),
            )


def _find_transaction_id(conn: sqlite3.Connection, transaction: BalanceTransaction) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM shopee_transacoes
        WHERE data_movimento = ?
          AND tipo_transacao = ?
          AND descricao = ?
          AND COALESCE(pedido_id, '') = COALESCE(?, '')
          AND direcao = ?
          AND valor = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            transaction.data_movimento,
            transaction.tipo_transacao,
            transaction.descricao,
            transaction.pedido_id or None,
            transaction.direcao,
            transaction.valor,
        ),
    ).fetchone()
    return int(row["id"]) if row else None


def _reconcile_all_orders(conn: sqlite3.Connection) -> None:
    timestamp = now_iso()

    conn.execute(
        """
        UPDATE shopee_pedidos_financeiros
        SET valor_pago_real = 0,
            data_liberacao_shopee = NULL,
            diferenca = 0,
            status_financeiro = 'em_espera',
            atualizado_em = ?
        """,
        (timestamp,),
    )

    payments = conn.execute(
        """
        SELECT
            pedido_id,
            SUM(valor) AS valor_pago,
            MIN(data_movimento) AS primeira_liberacao
        FROM shopee_transacoes
        WHERE pedido_id IS NOT NULL
          AND TRIM(pedido_id) <> ''
          AND LOWER(direcao) = 'entrada'
          AND LOWER(tipo_transacao) NOT LIKE '%saque%'
        GROUP BY pedido_id
        """
    ).fetchall()

    for payment in payments:
        order = conn.execute(
            """
            SELECT pedido_id, valor_liquido_estimado
            FROM shopee_pedidos_financeiros
            WHERE pedido_id = ?
            """,
            (payment["pedido_id"],),
        ).fetchone()
        if not order:
            continue

        valor_pago = float(payment["valor_pago"] or 0)
        estimado = float(order["valor_liquido_estimado"] or 0)
        diferenca = round(valor_pago - estimado, 2)
        status = "liberado" if abs(diferenca) <= 0.05 else "divergente"

        conn.execute(
            """
            UPDATE shopee_pedidos_financeiros
            SET valor_pago_real = ?,
                data_liberacao_shopee = ?,
                diferenca = ?,
                status_financeiro = ?,
                atualizado_em = ?
            WHERE pedido_id = ?
            """,
            (
                valor_pago,
                payment["primeira_liberacao"],
                diferenca,
                status,
                timestamp,
                payment["pedido_id"],
            ),
        )

    conn.execute(
        """
        UPDATE shopee_transacoes
        SET status_conciliacao = CASE
            WHEN LOWER(tipo_transacao) LIKE '%saque%' THEN 'saque'
            WHEN pedido_id IS NULL OR TRIM(pedido_id) = '' THEN 'sem_pedido'
            WHEN EXISTS (
                SELECT 1 FROM shopee_pedidos_financeiros p
                WHERE p.pedido_id = shopee_transacoes.pedido_id
            ) THEN 'conciliado'
            ELSE 'sem_pedido'
        END
        """
    )

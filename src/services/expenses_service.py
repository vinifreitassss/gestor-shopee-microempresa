from datetime import date

from src.database import fetch_all, get_connection, now_iso
from src.utils import mes_referencia_from_date


def list_expenses(mes_referencia: str) -> list[dict]:
    return fetch_all(
        """
        SELECT id, data, categoria, descricao, valor, criado_em
        FROM despesas
        WHERE mes_referencia = ?
        ORDER BY data DESC, id DESC
        """,
        (mes_referencia,),
    )


def add_expense(data: date, categoria: str, descricao: str, valor: float) -> None:
    mes_ref = mes_referencia_from_date(data)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO despesas (data, mes_referencia, categoria, descricao, valor, criado_em)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (data.isoformat(), mes_ref, categoria, descricao, valor, now_iso()),
        )


def delete_expense(expense_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM despesas WHERE id = ?", (expense_id,))
        return cur.rowcount > 0


def list_recurring_expenses() -> list[dict]:
    return fetch_all(
        """
        SELECT id, categoria, descricao, valor_padrao, dia_vencimento, frequencia, ativo
        FROM despesas_recorrentes
        WHERE ativo = 1
        ORDER BY categoria, descricao
        """
    )


def add_recurring_expense(categoria: str, descricao: str, valor: float, dia_vencimento: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO despesas_recorrentes (
                categoria, descricao, valor_padrao, dia_vencimento, frequencia, ativo, criado_em
            ) VALUES (?, ?, ?, ?, 'mensal', 1, ?)
            """,
            (categoria, descricao, valor, dia_vencimento, now_iso()),
        )


def deactivate_recurring_expense(recurring_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE despesas_recorrentes SET ativo = 0 WHERE id = ?",
            (recurring_id,),
        )
        return cur.rowcount > 0


def generate_recurring_for_month(mes_referencia: str) -> int:
    year, month = [int(part) for part in mes_referencia.split("-")]
    recurring = list_recurring_expenses()
    created = 0
    with get_connection() as conn:
        for item in recurring:
            day = min(int(item["dia_vencimento"]), 28)
            expense_date = date(year, month, day)
            exists = conn.execute(
                """
                SELECT id FROM despesas
                WHERE mes_referencia = ? AND recorrente_id = ?
                """,
                (mes_referencia, item["id"]),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO despesas (
                    data, mes_referencia, categoria, descricao, valor, recorrente_id, criado_em
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expense_date.isoformat(),
                    mes_referencia,
                    item["categoria"],
                    item["descricao"],
                    item["valor_padrao"],
                    item["id"],
                    now_iso(),
                ),
            )
            created += 1
    return created

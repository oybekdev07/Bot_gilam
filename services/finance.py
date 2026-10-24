"""Kirim (mijoz to'lovlari) va chiqim (oylik, yoqilg'i, ovqat va boshqalar) hisobi."""
from datetime import timedelta

from services.google_sheets import EXPENSES, INCOME, PAYMENTS, get_db
from services.store import get_kv
from services.utils import FMT, money, now, now_str, num, rand_id

# To'lov usullari (yetkazishda)
PAY_METHODS = {
    "cash": "💵 To'liq naqd",
    "card": "💳 To'liq karta",
    "half": "💵💳 Yarim naqd / yarim karta",
    "credit": "📝 Nasiya (qarz)",
    "mixed": "🔀 Aralash (izoh bilan)",
}

EXPENSE_CATEGORIES = {
    "salary": "👤 Xodim oyligi",
    "fuel": "⛽️ Yoqilg'i / gaz",
    "oil": "🛢 Moy almashtirish",
    "food": "🍽 Ovqat / abetka",
    "repair": "🔧 Ta'mirlash",
    "rent": "🏠 Ijara",
    "other": "📦 Boshqa",
}


async def record_order_income(
    order: dict,
    method: str,
    cash: float,
    card: float,
    credit: float,
    notes: str,
    actor_id,
) -> tuple[bool, str]:
    """Yetkazish yakunida mijoz to'lovini kirimga yozadi (bir marta)."""
    oid = order["order_id"]
    income_id = f"INC-{oid}"
    db = get_db()
    if any(r["income_id"] == income_id for r in await db.rows(INCOME)):
        return False, "Bu buyurtma uchun kirim allaqachon yozilgan."
    kv = get_kv()
    if not await kv.set(f"inc:{income_id}", "1", nx=True, ex=7 * 86400):
        return False, "Bu buyurtma uchun kirim allaqachon yozilmoqda."
    total = round(cash + card + credit, 2)
    try:
        await db.append(INCOME, {
            "income_id": income_id,
            "order_id": oid,
            "amount": total,
            "cash_amount": cash,
            "card_amount": card,
            "credit_amount": credit,
            "method": method,
            "notes": notes or "",
            "date": now_str(),
            "recorded_by": str(actor_id),
        })
    except Exception:
        await kv.delete(f"inc:{income_id}")
        raise
    return True, money(total)


async def add_expense(
    category: str,
    amount: float,
    notes: str,
    actor_id,
    related_payment_id: str = "",
) -> dict:
    """Qo'lda chiqim qo'shish (yoqilg'i, ovqat, ta'mirlash va h.k.)."""
    if category not in EXPENSE_CATEGORIES:
        category = "other"
    exp_id = rand_id("EXP", 6)
    row = {
        "expense_id": exp_id,
        "category": category,
        "amount": round(amount, 2),
        "notes": notes or "",
        "date": now_str(),
        "recorded_by": str(actor_id),
        "related_payment_id": related_payment_id or "",
    }
    await get_db().append(EXPENSES, row)
    return row


async def record_salary_expense(payment_id: str, amount: float, emp_name: str, actor_id) -> None:
    """Xodimga to'lov qilinganda avtomatik chiqim yozuvi."""
    # Dublikatdan himoya
    db = get_db()
    for r in await db.rows(EXPENSES):
        if r.get("related_payment_id") == payment_id:
            return
    await add_expense(
        "salary",
        amount,
        f"Oylik / komissiya: {emp_name}",
        actor_id,
        related_payment_id=payment_id,
    )


def _in_period(ts: str, start: str, end: str | None = None) -> bool:
    if not ts:
        return False
    if ts < start:
        return False
    if end and ts > end:
        return False
    return True


async def period_summary(period: str = "month") -> dict:
    """period: day | week | month | year | all"""
    n = now()
    midnight = n.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        start = midnight
        label = "📅 Bugun"
    elif period == "week":
        start = midnight - timedelta(days=n.weekday())
        label = "🗓 Shu hafta"
    elif period == "month":
        start = midnight.replace(day=1)
        label = "📆 Shu oy"
    elif period == "year":
        start = midnight.replace(month=1, day=1)
        label = "🗓 Shu yil"
    else:
        start = midnight.replace(year=2000)
        label = "📊 Hammasi"

    s = start.strftime(FMT)
    db = get_db()
    incomes = await db.rows(INCOME)
    expenses = await db.rows(EXPENSES)

    inc_rows = [r for r in incomes if _in_period(r.get("date", ""), s)]
    exp_rows = [r for r in expenses if _in_period(r.get("date", ""), s)]

    total_in = sum(num(r["amount"]) for r in inc_rows)
    cash_in = sum(num(r["cash_amount"]) for r in inc_rows)
    card_in = sum(num(r["card_amount"]) for r in inc_rows)
    credit_in = sum(num(r["credit_amount"]) for r in inc_rows)
    total_out = sum(num(r["amount"]) for r in exp_rows)

    by_cat: dict[str, float] = {}
    for r in exp_rows:
        cat = r.get("category") or "other"
        by_cat[cat] = by_cat.get(cat, 0) + num(r["amount"])

    return {
        "label": label,
        "period": period,
        "start": s,
        "income_total": round(total_in, 2),
        "income_cash": round(cash_in, 2),
        "income_card": round(card_in, 2),
        "income_credit": round(credit_in, 2),
        "income_count": len(inc_rows),
        "expense_total": round(total_out, 2),
        "expense_count": len(exp_rows),
        "expense_by_category": by_cat,
        "profit": round(total_in - total_out, 2),
        "recent_income": sorted(inc_rows, key=lambda r: r.get("date", ""), reverse=True)[:10],
        "recent_expenses": sorted(exp_rows, key=lambda r: r.get("date", ""), reverse=True)[:10],
    }


async def employee_period_earnings(tid, period: str = "month") -> dict:
    """Xodimning haftalik / oylik / yillik hisoblangan daromadi."""
    from services.google_sheets import EARNINGS

    n = now()
    midnight = n.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        start = midnight - timedelta(days=n.weekday())
        label = "Shu hafta"
    elif period == "year":
        start = midnight.replace(month=1, day=1)
        label = "Shu yil"
    else:
        start = midnight.replace(day=1)
        label = "Shu oy"

    s = start.strftime(FMT)
    rows = [
        r for r in await get_db().rows(EARNINGS)
        if r["employee_id"] == str(tid) and _in_period(r.get("date", ""), s)
    ]
    total = sum(num(r["amount"]) for r in rows)
    by_task: dict[str, float] = {}
    for r in rows:
        t = r.get("task_type") or "?"
        by_task[t] = by_task.get(t, 0) + num(r["amount"])
    return {
        "label": label,
        "period": period,
        "total": round(total, 2),
        "count": len(rows),
        "by_task": by_task,
        "rows": sorted(rows, key=lambda r: r.get("date", ""), reverse=True),
    }


async def list_expenses(limit: int = 20) -> list[dict]:
    rows = await get_db().rows(EXPENSES)
    return sorted(rows, key=lambda r: r.get("date", ""), reverse=True)[:limit]


async def list_income(limit: int = 20) -> list[dict]:
    rows = await get_db().rows(INCOME)
    return sorted(rows, key=lambda r: r.get("date", ""), reverse=True)[:limit]

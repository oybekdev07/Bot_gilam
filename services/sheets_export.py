"""SQLite'dagi ma'lumotlarni Google Sheets'ga o'tkazish (eksport).

Har bir varaq SQLite'dagi holat bilan TO'LIQ almashtiriladi (shuning uchun tugmani ko'p marta
bosish dublikat yaratmaydi). Sheets'da qo'lda yozilgan o'zgarishlar ustidan yoziladi —
asosiy baza har doim SQLite.
"""
import asyncio
import logging

import config
from services.google_sheets import SCHEMA, GoogleSheetsBackend, _retry, get_db

log = logging.getLogger(__name__)

# Sheets'da son bo'lib turishi kerak bo'lgan ustunlar (qolganlari matn: telefon, ID, sana ...)
NUMERIC = {
    "Orders": {"carpet_count", "total_area", "estimated_price", "final_price", "collection_commission",
               "washing_payment", "finishing_payment", "delivery_commission", "latitude", "longitude",
               "payment_cash", "payment_card", "payment_credit"},
    "Employees": {"base_salary"},
    "Employee Earnings": {"amount"},
    "Salary Payments": {"amount_paid"},
    "Income": {"amount", "cash_amount", "card_amount", "credit_amount"},
    "Expenses": {"amount"},
}
CHUNK = 2000


def _cell(table: str, col: str, v: str):
    if v == "":
        return ""
    if col in NUMERIC.get(table, ()):
        try:
            f = float(v)
            return int(f) if f.is_integer() else f
        except ValueError:
            return v
    return v


def _export_sync() -> dict[str, int]:
    gs = GoogleSheetsBackend()   # ulanishda xato bo'lsa shu yerda chiqadi
    gs._ensure()                 # varaqlar va sarlavhalar mavjudligini ta'minlaydi
    db = get_db()
    counts: dict[str, int] = {}
    for name, headers in SCHEMA.items():
        rows = db.all_rows_sync(name)
        values = [[_cell(name, h, r.get(h, "")) for h in headers] for r in rows]
        ws = gs._worksheet(name)
        _retry(ws.resize, rows=max(1000, len(values) + 50), cols=max(len(headers), 10))
        _retry(ws.clear)
        _retry(ws.update, values=[headers], range_name="A1", value_input_option="RAW")
        for i in range(0, len(values), CHUNK):
            part = values[i:i + CHUNK]
            _retry(ws.update, values=part, range_name=f"A{i + 2}", value_input_option="RAW")
        try:
            ws.freeze(rows=1)
        except Exception:  # noqa: BLE001
            pass
        counts[name] = len(values)
    return counts


async def export_all() -> dict[str, int]:
    """Barcha jadvallarni Google Sheets'ga yozadi. {varaq_nomi: qatorlar_soni} qaytaradi."""
    return await asyncio.to_thread(_export_sync)


def sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{config.GOOGLE_SHEET_ID}/edit"

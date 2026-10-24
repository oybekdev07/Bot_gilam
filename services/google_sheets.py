"""Jadval sxemasi va asosiy baza (faqat SQLite).

Google Sheets olib tashlangan — barcha ma'lumotlar data/carpet.db da.
Boshqa modullar SCHEMA / get_db / ensure_once ni shu yerdan import qiladi.
"""
import config

ORDERS = "Orders"
CUSTOMERS = "Customers"
EMPLOYEES = "Employees"
EARNINGS = "Employee Earnings"
PAYMENTS = "Salary Payments"
HISTORY = "Order History"
SETTINGS = "Settings"
INCOME = "Income"
EXPENSES = "Expenses"

SCHEMA_VERSION = "v2"

SCHEMA: dict[str, list[str]] = {
    ORDERS: [
        "order_id", "customer_id", "customer_name", "phone", "pickup_address", "latitude", "longitude",
        "carpet_count", "dimensions_json", "total_area", "carpet_type", "instructions",
        "estimated_price", "final_price", "collection_driver_id", "washing_employee_id",
        "finishing_employee_id", "delivery_driver_id", "collection_commission", "washing_payment",
        "finishing_payment", "delivery_commission", "status", "created_by", "created_at",
        "collected_at", "washing_started_at", "washing_completed_at", "finishing_started_at",
        "finishing_completed_at", "delivery_started_at", "delivered_at", "updated_at",
        "payment_method", "payment_cash", "payment_card", "payment_credit", "payment_notes", "payment_status",
    ],
    CUSTOMERS: ["customer_id", "full_name", "phone", "address", "order_ids", "created_at"],
    EMPLOYEES: [
        "telegram_id", "username", "full_name", "role", "active", "salary_type", "base_salary",
        "commission_type", "commission_value", "created_at",
    ],
    EARNINGS: ["transaction_id", "employee_id", "order_id", "task_type", "amount", "date", "payment_status"],
    PAYMENTS: ["payment_id", "employee_id", "amount_paid", "payment_date", "payment_method", "notes", "admin_id"],
    HISTORY: ["order_id", "previous_status", "new_status", "employee_telegram_id", "employee_name",
              "timestamp", "action_details"],
    SETTINGS: ["key", "value", "description"],
    INCOME: [
        "income_id", "order_id", "amount", "cash_amount", "card_amount", "credit_amount",
        "method", "notes", "date", "recorded_by",
    ],
    EXPENSES: [
        "expense_id", "category", "amount", "notes", "date", "recorded_by", "related_payment_id",
    ],
}

DEFAULT_SETTINGS = [
    ("price_per_m2", "15000", "1 m² uchun tavsiya etilgan narx (so'm)"),
    ("collection_pay_type", "percent", "Olib ketish haqi turi: fixed / percent / per_m2"),
    ("collection_pay_value", "5", "Olib ketish haqi qiymati (percent=%, fixed=so'm, per_m2=so'm/m²)"),
    ("washing_pay_type", "per_m2", "Yuvish haqi turi: fixed / percent / per_m2"),
    ("washing_pay_value", "2000", "Yuvish haqi qiymati"),
    ("finishing_pay_type", "per_m2", "Pardozlash haqi turi: fixed / percent / per_m2"),
    ("finishing_pay_value", "1500", "Pardozlash haqi qiymati"),
    ("delivery_pay_type", "percent", "Yetkazish haqi turi: fixed / percent / per_m2"),
    ("delivery_pay_value", "5", "Yetkazish haqi qiymati"),
]


def _s(v) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return "" if v is None else str(v)


_db = None
_ensured = False


def get_db():
    """Asosiy baza — SQLite."""
    global _db
    if _db is None:
        from services.sqlite_backend import SQLiteBackend
        _db = SQLiteBackend()
    return _db


async def ensure_once(kv=None):
    """Baza jadvallari mavjudligini bir marta tekshiradi."""
    global _ensured
    if _ensured:
        return
    await get_db().ensure()
    _ensured = True

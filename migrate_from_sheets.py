"""Bir martalik ko'chirish: Google Sheets'dagi eski ma'lumotlarni SQLite bazaga o'tkazadi.

Ishga tushirish:   python migrate_from_sheets.py
Baza bo'sh bo'lmasa, to'xtaydi (ustiga yozmaslik uchun). Majburan: python migrate_from_sheets.py --force
(--force mavjud bazani tozalab, Sheets'dagi holatni qayta yuklaydi.)
"""
import sys

import config
from services.google_sheets import SCHEMA, SETTINGS, GoogleSheetsBackend, get_db


def main() -> int:
    if not config.sheets_configured():
        print("❌ .env da GOOGLE_SHEET_ID va GOOGLE_SERVICE_ACCOUNT_FILE to'ldirilmagan.")
        return 1
    db = get_db()
    db._ensure()
    force = "--force" in sys.argv
    has_data = any(db._rows(t) for t in SCHEMA if t != SETTINGS)
    if has_data and not force:
        print("⚠️ SQLite bazada allaqachon ma'lumot bor. Ustiga yozmaslik uchun to'xtadim.\n"
              "   Baribir yuklash uchun: python migrate_from_sheets.py --force")
        return 1
    print("📥 Google Sheets'dan o'qilmoqda...")
    gs = GoogleSheetsBackend()
    gs._ensure()
    total = 0
    for name in SCHEMA:
        rows = gs._rows(name)
        with db._lock:
            db._conn.execute(f'DELETE FROM "{name}"')
        for r in rows:
            db._append(name, r)
        total += len(rows)
        print(f"   {name}: {len(rows)} qator")
    print(f"✅ Tayyor: jami {total} qator SQLite'ga ko'chirildi ({config.DB_PATH}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

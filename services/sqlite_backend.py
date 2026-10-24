"""Asosiy baza — SQLite (bitta fayl: data/carpet.db).

Interfeys GoogleSheetsBackend bilan bir xil (ensure / rows / append / update), shuning uchun
qolgan kod (orders, employees, salaries) o'zgarishsiz ishlaydi. Barcha ustunlar matn (TEXT)
sifatida saqlanadi — xuddi Google Sheets'dagidek.
"""
import asyncio
import os
import sqlite3
import threading

import config
from services.google_sheets import DEFAULT_SETTINGS, SCHEMA, SETTINGS, _s


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class SQLiteBackend:
    def __init__(self, path: str | None = None):
        self.path = path or config.DB_PATH
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)  # avto-commit
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")

    # ---------- sinxron ichki funksiyalar
    def _ensure(self):
        with self._lock:
            c = self._conn
            for name, headers in SCHEMA.items():
                cols = ", ".join(f"{_q(h)} TEXT NOT NULL DEFAULT ''" for h in headers)
                c.execute(f"CREATE TABLE IF NOT EXISTS {_q(name)} ({cols})")
                have = {r["name"] for r in c.execute(f"PRAGMA table_info({_q(name)})")}
                for h in headers:
                    if h not in have:  # yangi ustun qo'shilgan bo'lsa — mavjud ma'lumot buzilmaydi
                        c.execute(f"ALTER TABLE {_q(name)} ADD COLUMN {_q(h)} TEXT NOT NULL DEFAULT ''")
                idx = "idx_" + name.replace(" ", "_") + "_" + headers[0]
                c.execute(f"CREATE INDEX IF NOT EXISTS {_q(idx)} ON {_q(name)} ({_q(headers[0])})")
            have_keys = {r["key"] for r in self._rows(SETTINGS)}
            for k, v, d in DEFAULT_SETTINGS:
                if k not in have_keys:
                    c.execute(f"INSERT INTO {_q(SETTINGS)} (key, value, description) VALUES (?, ?, ?)", (k, v, d))

    def _rows(self, name: str) -> list[dict]:
        headers = SCHEMA[name]
        with self._lock:
            cur = self._conn.execute(f"SELECT * FROM {_q(name)} ORDER BY rowid")
            return [{h: (r[h] if r[h] is not None else "") for h in headers} for r in cur.fetchall()]

    def _append(self, name: str, row: dict):
        headers = SCHEMA[name]
        marks = ", ".join("?" for _ in headers)
        cols = ", ".join(_q(h) for h in headers)
        with self._lock:
            self._conn.execute(f"INSERT INTO {_q(name)} ({cols}) VALUES ({marks})", [_s(row.get(h, "")) for h in headers])

    def _update(self, name: str, key_col: str, key: str, updates: dict) -> bool:
        headers = SCHEMA[name]
        if key_col not in headers:
            return False
        data = {c: _s(v) for c, v in updates.items() if c in headers}
        with self._lock:
            exists = self._conn.execute(
                f"SELECT rowid FROM {_q(name)} WHERE {_q(key_col)} = ? ORDER BY rowid LIMIT 1", (str(key),)).fetchone()
            if exists is None:
                return False
            if data:
                sets = ", ".join(f"{_q(c)} = ?" for c in data)
                self._conn.execute(f"UPDATE {_q(name)} SET {sets} WHERE rowid = ?", [*data.values(), exists["rowid"]])
            return True

    # ---------- asinxron interfeys (Google Sheets bilan bir xil)
    async def ensure(self):
        await asyncio.to_thread(self._ensure)

    async def rows(self, name: str) -> list[dict]:
        return await asyncio.to_thread(self._rows, name)

    async def append(self, name: str, row: dict):
        await asyncio.to_thread(self._append, name, row)

    async def update(self, name: str, key_col: str, key: str, updates: dict) -> bool:
        return await asyncio.to_thread(self._update, name, key_col, key, updates)

    # ---------- eksport uchun sinxron o'qish (alohida oqimdan chaqiriladi)
    def all_rows_sync(self, name: str) -> list[dict]:
        return self._rows(name)

    def close(self):
        with self._lock:
            self._conn.close()

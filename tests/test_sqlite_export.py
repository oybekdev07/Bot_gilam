"""SQLite + parser + Google Sheets eksporti testlari (internet va haqiqiy Telegram kerak emas).
Ishga tushirish:  python tests/test_sqlite_export.py"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime

TMP = tempfile.mkdtemp()
os.environ.update({"BOT_TOKEN": "123456:TESTTOKEN", "ADMIN_IDS": "1001", "GOOGLE_SHEET_ID": "sheet123",
                   "GOOGLE_SERVICE_ACCOUNT_JSON": "{}", "DB_PATH": os.path.join(TMP, "t.db")})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import Chat, Message  # noqa: E402

import bot as botmod  # noqa: E402
from services import employees, google_sheets, orders, sheets_export  # noqa: E402
from services.google_sheets import ORDERS, SCHEMA  # noqa: E402
from services.order_parser import parse_order_text  # noqa: E402

PASSED, FAILED = [], []
LOG = []


def check(name, cond, extra=""):
    (PASSED if cond else FAILED).append(name)
    print(("PASS  " if cond else "FAIL  ") + name + (f"  [{extra}]" if extra and not cond else ""))


# ---------------------------------------------------------------- 1. parser
def test_parser():
    def P(t):
        return parse_order_text(t)

    d, e = P("Ali Valiyev, 91 123 45 67, Chilonzor 5-kvartal, 12-uy, 3 ta, jun, dog' bor")
    check("parser: vergul bilan (ism birinchi)", not e and d["name"] == "Ali Valiyev" and d["phone"] == "+998911234567"
          and d["address"] == "Chilonzor 5-kvartal, 12-uy" and d["count"] == 3 and d["ctype"] == "Jun"
          and d["instr"] == "dog' bor", str((d, e)))
    d, e = P("91 123 45 67, Chilonzor 5-kvartal 12-uy, 3 ta gilam, ipak, Ali Valiyev")
    check("parser: ism OXIRIDA bo'lsa ham taniydi", not e and d["name"] == "Ali Valiyev" and d["ctype"] == "Ipak"
          and d["address"] == "Chilonzor 5-kvartal 12-uy" and d["count"] == 3, str((d, e)))
    d, e = P("3 ta, Sintetik, Karim Aliyev, Yunusobod 4-mavze 8-uy, 901234567")
    check("parser: aralash tartib", not e and d["name"] == "Karim Aliyev" and d["count"] == 3
          and d["ctype"] == "Sintetik" and "Yunusobod" in d["address"], str((d, e)))
    d, e = P("Ali Valiyev\n91 123 45 67\nChilonzor 5-kvartal, 12-uy\n3 ta gilam\nJun\ndog' bor")
    check("parser: eski (yangi qatorli) usul ishlaydi", not e and d["name"] == "Ali Valiyev" and d["count"] == 3
          and d["instr"] == "dog' bor", str((d, e)))
    d, e = P("Ism: Ali, Tel: 901234567, Manzil: Chilonzor, 5-kvartal, 12-uy, Soni: 2, Turi: ipak")
    check("parser: Ism:/Tel:/Manzil: yorliqlari + vergul", not e and d["address"] == "Chilonzor, 5-kvartal, 12-uy"
          and d["count"] == 2 and d["ctype"] == "Ipak", str((d, e)))
    d, e = P("Dilnoza Karimova, 935551122, Sergeli 7-mavze 15-uy, 41.2995, 69.2401, 2 ta, oddiy")
    check("parser: koordinata joylashuvga (vergul bo'linmaydi)", not e and d["lat"] == 41.2995 and d["lon"] == 69.2401
          and d["address"] == "Sergeli 7-mavze 15-uy", str((d, e)))
    d, e = P("O'ktam, 901112233, Qatortol ko'chasi 3-uy, 5 ta, https://maps.google.com/?q=41.311081,69.240562")
    check("parser: xarita havolasi joylashuvga", not e and d["lat"] == 41.311081 and d["name"] == "O'ktam", str((d, e)))
    d, e = P("Ali Valiyev, 901234567, Chilonzor")
    check("parser: gilam soni yo'q -> xato", any("soni" in x for x in e))
    d, e = P("Ali, 90 123 45, Chilonzor 5, 3 ta")
    check("parser: noto'g'ri telefon -> xato", any("Telefon" in x for x in e))
    d, e = P("+998 90 123 45 67, Ali Valiyev, Chilonzor 5, 2 ta")
    check("parser: +998 bilan telefon", not e and d["phone"] == "+998901234567", str((d, e)))


# ---------------------------------------------------------------- 2. baza + buyurtma
async def test_db():
    db = google_sheets.get_db()
    await db.ensure()
    check("SQLite: standart sozlamalar yaratildi", len(await db.rows("Settings")) >= 9)
    await db.append("Employees", {"telegram_id": 5, "full_name": "Test", "role": "washer", "active": True, "base_salary": 0.0})
    r = (await db.rows("Employees"))[0]
    check("SQLite: append/rows (bool -> TRUE, 0.0 -> 0)", r["active"] == "TRUE" and r["base_salary"] == "0" and r["telegram_id"] == "5", str(r))
    ok = await db.update("Employees", "telegram_id", "5", {"full_name": "Yangi", "yoq_ustun": "x"})
    check("SQLite: update", ok and (await db.rows("Employees"))[0]["full_name"] == "Yangi")
    check("SQLite: yo'q kalit -> False", not await db.update("Employees", "telegram_id", "999", {"full_name": "z"}))

    d = {"name": "Ali Valiyev", "phone": "+998911234567", "address": "Chilonzor 5", "count": 2, "ctype": "Jun",
         "instr": "", "dims": [], "price": 0, "lat": None, "lon": None}
    actor = {"telegram_id": "1001", "full_name": "Ega", "role": "owner"}
    o = await orders.create_order(d, actor)
    row = (await db.rows(ORDERS))[0]
    check("create_order SQLite'ga yozdi", row["order_id"] == o["order_id"] and row["status"] == "new" and row["latitude"] == "")
    o2 = await orders.create_order({**d, "name": "Ali V."}, actor)
    cust = await db.rows("Customers")
    check("Mijoz telefon bo'yicha qayta ishlatildi (1 ta mijoz, 2 buyurtma)",
          len(cust) == 1 and len(cust[0]["order_ids"].split(",")) == 2, str(cust))

    await db.update(ORDERS, "order_id", o["order_id"], {"status": "collected"})
    wr = {"telegram_id": "4001", "full_name": "Yuvuvchi", "role": "washer"}
    res = await orders.set_dimensions(o["order_id"], [[3, 2], [2.5, 1.8]], wr)
    r = (await db.rows(ORDERS))[0]
    check("set_dimensions: maydon 10.5 va narx 10.5×15000", res.ok and r["total_area"] == "10.5" and r["estimated_price"] == "157500", str((res.msg, r["total_area"], r["estimated_price"])))
    bad = await orders.set_dimensions(o["order_id"], [[1, 1]], {"telegram_id": "9", "full_name": "x", "role": "collector"})
    check("set_dimensions: ruxsatsiz rol rad etildi", not bad.ok)


# ---------------------------------------------------------------- 3. eksport (soxta Google Sheets)
class FakeWS:
    def __init__(self, title):
        self.title, self.data, self.resized = title, [], None

    def resize(self, rows=None, cols=None):
        self.resized = (rows, cols)

    def clear(self):
        self.data = []

    def update(self, values=None, range_name=None, value_input_option=None):
        assert value_input_option == "RAW"
        start = int(range_name[1:]) - 1
        self.data[start:start + len(values)] = values

    def freeze(self, rows=0):
        pass


class FakeSheets:
    instances = []

    def __init__(self):
        self.ws = {n: FakeWS(n) for n in SCHEMA}
        FakeSheets.instances.append(self)

    def _ensure(self):
        pass

    def _worksheet(self, name):
        return self.ws[name]


async def test_export():
    sheets_export.GoogleSheetsBackend = FakeSheets
    counts = await sheets_export.export_all()
    fs = FakeSheets.instances[-1]
    ws = fs.ws[ORDERS]
    head = ws.data[0]
    check("eksport: sarlavha + 2 buyurtma yozildi", head == SCHEMA[ORDERS] and len(ws.data) == 3 and counts[ORDERS] == 2, str(counts))
    r = dict(zip(head, ws.data[1]))
    check("eksport: sonlar son bo'lib (10.5, 157500, 2), telefon matn",
          r["total_area"] == 10.5 and r["estimated_price"] == 157500 and r["carpet_count"] == 2 and r["phone"] == "+998911234567", str(r))
    await sheets_export.export_all()
    check("eksport: qayta bosilsa dublikat yo'q", len(FakeSheets.instances[-1].ws[ORDERS].data) == 3)


# ---------------------------------------------------------------- 4. bot oqimi (soxta Telegram)
class FakeSession(BaseSession):
    async def close(self):
        pass

    async def stream_content(self, *a, **k):
        yield b""

    async def make_request(self, bot, method, timeout=None):
        name = type(method).__name__
        if name in ("SendMessage", "EditMessageText"):
            chat_id = getattr(method, "chat_id", 0)
            LOG.append((chat_id, method.text, method.reply_markup))
            return Message(message_id=len(LOG) + 10, date=datetime.now(), chat=Chat(id=chat_id, type="private"), text=method.text)
        return True


botmod.make_bot = lambda: Bot(token="123456:TESTTOKEN", session=FakeSession(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
_n = [100]


def msg(uid, text):
    _n[0] += 1
    m = {"message_id": _n[0], "date": 0, "chat": {"id": uid, "type": "private"},
         "from": {"id": uid, "is_bot": False, "first_name": f"U{uid}"}, "text": text}
    if text.startswith("/"):
        m["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    return {"update_id": _n[0], "message": m}


def cb(uid, data):
    _n[0] += 1
    return {"update_id": _n[0], "callback_query": {
        "id": str(_n[0]), "from": {"id": uid, "is_bot": False, "first_name": f"U{uid}"}, "chat_instance": "x", "data": data,
        "message": {"message_id": 1, "date": 0, "chat": {"id": uid, "type": "private"}, "text": "x"}}}


def last(uid):
    return [t for c, t, _ in LOG if c == uid]


async def test_bot():
    db = google_sheets.get_db()
    await employees.add_employee(2001, "Operator Ali", "operator")
    await employees.add_employee(3001, "Haydovchi Bobur", "collector")
    before = len(await db.rows(ORDERS))
    await botmod.process_update(cb(2001, "m:newo"))
    await botmod.process_update(msg(2001, "91 123 45 67, Chilonzor 5-kvartal 12-uy, 3 ta gilam, ipak, Ali Valiyev"))
    summ = [t for t in last(2001) if "Buyurtma xulosasi" in t]
    check("bot: bitta xabar (vergul, ism oxirida) -> xulosa", bool(summ) and "Ali Valiyev" in summ[-1] and "3 ta" in summ[-1] and "Ipak" in summ[-1], str(last(2001)[-1:]))
    await botmod.process_update(cb(2001, "no:swap"))
    sw = [t for t in last(2001) if "Buyurtma xulosasi" in t][-1]
    check("bot: Ism ↔ Manzil almashtirish tugmasi", "Chilonzor 5-kvartal 12-uy" in sw.split("📞")[0], sw)
    await botmod.process_update(cb(2001, "no:swap"))
    await botmod.process_update(cb(2001, "no:ok"))
    rows = await db.rows(ORDERS)
    check("bot: tasdiqlangach SQLite'ga yozildi", len(rows) == before + 1 and rows[-1]["customer_name"] == "Ali Valiyev"
          and rows[-1]["pickup_address"] == "Chilonzor 5-kvartal 12-uy" and rows[-1]["carpet_type"] == "Ipak"
          and rows[-1]["carpet_count"] == "3" and rows[-1]["phone"] == "+998911234567", str(rows[-1:]))
    check("bot: haydovchiga xabar ketdi", any("Yangi buyurtma" in t for t in last(3001)))

    # Google Sheetga o'tkazish tugmasi (faqat admin)
    LOG.clear()
    await botmod.process_update(cb(1001, "a:gsx"))
    check("bot: «Google Sheetga» tasdiqlash oynasi", any("Google Sheetga o'tkazish" in t for t in last(1001)))
    await botmod.process_update(cb(1001, "a:gsy"))
    done = [t for t in last(1001) if "o'tkazildi" in t]
    check("bot: eksport muvaffaqiyatli, qatorlar soni ko'rsatildi", bool(done) and "Orders: <b>" in done[-1], str(last(1001)[-2:]))
    LOG.clear()
    await botmod.process_update(cb(2001, "a:gsy"))
    check("bot: operator eksport qila olmaydi", not any("o'tkazildi" in t for t in last(2001)))
    menu = [m for c, _, m in LOG if c == 1001]
    await botmod.process_update(msg(1001, "/start"))
    check("bot: admin menyuda «Google Sheetga» tugmasi bor", "a:gsx" in str([m for c, _, m in LOG if c == 1001][-1]))


async def main():
    test_parser()
    await test_db()
    await test_export()
    await test_bot()
    print(f"\n{len(PASSED)} o'tdi, {len(FAILED)} yiqildi")
    for f in FAILED:
        print("  ✗", f)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

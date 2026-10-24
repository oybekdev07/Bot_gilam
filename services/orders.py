"""Buyurtma yaratish, bosqichlar, biriktirish va statistika.

Bir buyurtmani bir vaqtda ikki kishi o'zgartira olmasligi uchun har bir yozuv
amali Redis qulfi (kv.lock) ichida bajariladi va holat Google Sheets'dan
QULF ICHIDA qayta o'qiladi. Shu tufayli "ikki haydovchi bitta buyurtmani oladi"
holati yuzaga kelmaydi.
"""
import json
import re
from dataclasses import dataclass
from datetime import timedelta

from services import employees, salaries
from services.constants import COMMISSION_COL, REASSIGN, STAGES, STATUS_LABELS
from services.google_sheets import CUSTOMERS, EARNINGS, HISTORY, ORDERS, get_db
from services.store import LockBusy, get_kv  # noqa: F401
from services.utils import FMT, now, now_str, num, rand_id


@dataclass
class Result:
    ok: bool
    msg: str = ""
    order: dict | None = None


# ------------------------------------------------------------------ o'qish
async def get_order(order_id: str) -> dict | None:
    for o in await get_db().rows(ORDERS):
        if o["order_id"] == order_id:
            return o
    return None


async def list_orders(statuses: list[str] | None = None, who_col: str | None = None,
                      who_id=None, created_by=None) -> list[dict]:
    out = []
    for o in await get_db().rows(ORDERS):
        if statuses and o["status"] not in statuses:
            continue
        if who_col and str(o.get(who_col)) != str(who_id):
            continue
        if created_by is not None and str(o.get("created_by")) != str(created_by):
            continue
        out.append(o)
    return sorted(out, key=lambda o: o["created_at"], reverse=True)


async def search_orders(q: str) -> list[dict]:
    q = q.strip().lower()
    digits = re.sub(r"\D", "", q)
    out = []
    for o in await get_db().rows(ORDERS):
        if (q and q in o["order_id"].lower()) or (q and q in o["customer_name"].lower()) \
                or (len(digits) >= 3 and digits in re.sub(r"\D", "", o["phone"])):
            out.append(o)
    return sorted(out, key=lambda o: o["created_at"], reverse=True)[:15]


async def history_of(order_id: str) -> list[dict]:
    rows = [h for h in await get_db().rows(HISTORY) if h["order_id"] == order_id]
    return sorted(rows, key=lambda h: h["timestamp"])


async def _log(order_id, prev, new, actor, details):
    await get_db().append(HISTORY, {
        "order_id": order_id, "previous_status": prev, "new_status": new,
        "employee_telegram_id": str(actor["telegram_id"]), "employee_name": actor.get("full_name", ""),
        "timestamp": now_str(), "action_details": details,
    })


# ------------------------------------------------------------------ yaratish
async def create_order(d: dict, creator: dict) -> dict:
    db = get_db()
    ts = now_str()
    phone = d.get("phone") or ""
    if not phone:
        raise ValueError("Telefon raqami yo'q")
    customer_id = None
    for c in await db.rows(CUSTOMERS):
        if c["phone"] == phone:
            customer_id = c["customer_id"]
            break
    existing = {o["order_id"] for o in await db.rows(ORDERS)}
    order_id = rand_id("ORD-" + now().strftime("%y%m%d"))
    while order_id in existing:
        order_id = rand_id("ORD-" + now().strftime("%y%m%d"))

    raw_dims = d.get("dims") or []
    dims = []
    for pair in raw_dims:
        try:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                l, w = float(pair[0]), float(pair[1])
                dims.append({"length": l, "width": w, "area": round(l * w, 2)})
        except (TypeError, ValueError):
            continue
    total = round(sum(x["area"] for x in dims), 2)

    # Mahsulotlar matni (gilam/adyol) — ctype yoki items_text
    ctype = (d.get("ctype") or d.get("items_text") or "").strip()
    if not ctype and d.get("items"):
        try:
            ctype = ", ".join(f"{it.get('type', '?')}: {it.get('count', 0)} ta" for it in d["items"])
        except Exception:
            ctype = ""

    if customer_id is None:
        customer_id = rand_id("C", 6)
        await db.append(CUSTOMERS, {
            "customer_id": customer_id, "full_name": d.get("name") or "", "phone": phone,
            "address": d.get("address") or "", "order_ids": order_id, "created_at": ts,
        })
    else:
        for c in await db.rows(CUSTOMERS):
            if c["customer_id"] == customer_id:
                ids = [x for x in c.get("order_ids", "").split(",") if x] + [order_id]
                await db.update(CUSTOMERS, "customer_id", customer_id,
                                {"order_ids": ",".join(ids),
                                 "address": d.get("address") or c.get("address") or "",
                                 "full_name": d.get("name") or c.get("full_name") or ""})
                break

    count = int(d.get("count") or len(dims) or 1)
    price = num(d.get("price"))
    row = {
        "order_id": order_id, "customer_id": customer_id,
        "customer_name": d.get("name") or "", "phone": phone,
        "pickup_address": d.get("address") or "",
        "latitude": d.get("lat", "") if d.get("lat") is not None else "",
        "longitude": d.get("lon", "") if d.get("lon") is not None else "",
        "carpet_count": count,
        "dimensions_json": json.dumps(dims, ensure_ascii=False),
        "total_area": total,
        "carpet_type": ctype,
        "instructions": d.get("instr") or "",
        "estimated_price": price, "final_price": "", "status": "new",
        "created_by": str(creator.get("telegram_id") or ""),
        "created_at": ts, "updated_at": ts,
    }
    await db.append(ORDERS, row)
    await _log(order_id, "-", "new", creator, "Buyurtma ro'yxatdan o'tkazildi")
    return row


# ------------------------------------------------------------------ bosqichlar
async def advance(order_id: str, act: str, actor: dict) -> Result:
    st = STAGES.get(act)
    if not st:
        return Result(False, "Noma'lum amal.")
    emp = await employees.get_actor(int(actor["telegram_id"]), fresh=True)
    if not emp or emp["role"] != st["role"]:
        return Result(False, "⛔ Sizda bu amalni bajarish huquqi yo'q.")
    tid = str(emp["telegram_id"])
    try:
        async with get_kv().lock(f"order:{order_id}"):
            o = await get_order(order_id)
            if not o:
                return Result(False, "Buyurtma topilmadi.")
            if o["status"] != st["frm"]:
                if st["claim"] and o["status"] not in ("cancelled",):
                    return Result(False, "⚠️ Bu buyurtma allaqachon boshqa xodimga biriktirilgan yoki holati o'zgargan.")
                return Result(False, "⚠️ Buyurtma holati mos emas (amal allaqachon bajarilgan bo'lishi mumkin).")
            if not st["claim"] and str(o.get(st["who"])) != tid:
                return Result(False, "⛔ Bu buyurtma sizga biriktirilmagan.")

            ts = now_str()
            updates = {"status": st["to"], "updated_at": ts}
            if st["claim"]:
                updates[st["who"]] = tid
            if st["ts"]:
                updates[st["ts"]] = ts
            if st["earn"]:
                task = st["earn"]
                amount = await salaries.record_earning(emp, o, task)
                updates[COMMISSION_COL[task]] = amount
            if not await get_db().update(ORDERS, "order_id", order_id, updates):
                return Result(False, "Jadvalni yangilab bo'lmadi, qayta urinib ko'ring.")
            o.update(updates)
            await _log(order_id, st["frm"], st["to"], emp, st["log"])
            return Result(True, "✅ " + st["log"] + ".", o)
    except LockBusy as e:
        return Result(False, str(e))


async def set_dimensions(order_id: str, dims: list, actor: dict) -> Result:
    """Yuvuvchi / pardozlovchi gilam o'lchamlarini saqlaydi (dims = [[uzunlik, eni], ...]).
    Jami maydon va taxminiy narx (maydon × 1 m² narxi) qayta hisoblanadi."""
    if actor["role"] not in ("owner", "admin", "washer", "finisher"):
        return Result(False, "⛔ Ruxsat yo'q.")
    try:
        async with get_kv().lock(f"order:{order_id}"):
            o = await get_order(order_id)
            if not o:
                return Result(False, "Buyurtma topilmadi.")
            if o["status"] not in ("collected", "washing", "washed", "finishing"):
                return Result(False, "⚠️ Bu bosqichda o'lchamlarni o'zgartirib bo'lmaydi.")
            items = [{"length": float(a), "width": float(b), "area": round(float(a) * float(b), 2)} for a, b in dims]
            total = round(sum(x["area"] for x in items), 2)
            price_m2 = num((await salaries.get_settings()).get("price_per_m2"))
            old_total = o.get("total_area") or "0"
            updates = {
                "dimensions_json": json.dumps(items, ensure_ascii=False),
                "total_area": total,
                "estimated_price": round(total * price_m2),
                "updated_at": now_str(),
            }
            if not await get_db().update(ORDERS, "order_id", order_id, updates):
                return Result(False, "Jadvalni yangilab bo'lmadi, qayta urinib ko'ring.")
            o.update({k: str(v) for k, v in updates.items()})
            await _log(order_id, o["status"], o["status"], actor,
                       f"O'lchamlar saqlandi: {old_total} → {total:g} m² ({len(items)} ta gilam)")
            return Result(True, "O'lchamlar saqlandi.", o)
    except LockBusy as e:
        return Result(False, str(e))


async def reassign(order_id: str, stage: str, new_emp: dict, admin: dict) -> Result:
    cfg = REASSIGN[stage]
    if admin["role"] not in ("owner", "admin"):
        return Result(False, "⛔ Faqat administrator qayta biriktira oladi.")
    fresh = await employees.get_employee(new_emp["telegram_id"], fresh=True)
    if not fresh or fresh.get("role") != cfg["role"] or not employees.is_active(fresh):
        return Result(False, "Tanlangan xodim bu vazifa uchun mos emas yoki faol emas.")
    try:
        async with get_kv().lock(f"order:{order_id}"):
            o = await get_order(order_id)
            if not o:
                return Result(False, "Buyurtma topilmadi.")
            if o["status"] not in cfg["statuses"]:
                return Result(False, "Bu bosqich allaqachon yakunlangan yoki hali boshlanmagan — qayta biriktirib bo'lmaydi.")
            old = o.get(cfg["col"]) or ""
            ts = now_str()
            updates = {cfg["col"]: str(fresh["telegram_id"]), "updated_at": ts}
            prev = o["status"]
            if prev == cfg["statuses"][0]:  # hali hech kim olmagan -> biriktirish bilan boshlanadi
                claim = STAGES[cfg["claim_act"]]
                updates["status"] = claim["to"]
                if claim["ts"]:
                    updates[claim["ts"]] = ts
            await get_db().update(ORDERS, "order_id", order_id, updates)
            o.update(updates)
            names = await employees.name_map()
            await _log(order_id, prev, o["status"], admin,
                       f"Biriktirildi: {names.get(str(old), old) or '—'} → {fresh['full_name']} ({stage})")
            return Result(True, "✅ Biriktirildi.", {**o, "_old": str(old)})
    except LockBusy as e:
        return Result(False, str(e))


async def cancel_order(order_id: str, admin: dict) -> Result:
    if admin["role"] not in ("owner", "admin"):
        return Result(False, "⛔ Ruxsat yo'q.")
    try:
        async with get_kv().lock(f"order:{order_id}"):
            o = await get_order(order_id)
            if not o:
                return Result(False, "Buyurtma topilmadi.")
            if o["status"] in ("delivered", "cancelled"):
                return Result(False, "Bu buyurtmani bekor qilib bo'lmaydi.")
            await get_db().update(ORDERS, "order_id", order_id, {"status": "cancelled", "updated_at": now_str()})
            await _log(order_id, o["status"], "cancelled", admin, "Administrator buyurtmani bekor qildi")
            o["status"] = "cancelled"
            return Result(True, "Buyurtma bekor qilindi.", o)
    except LockBusy as e:
        return Result(False, str(e))


async def set_final_price(order_id: str, price: float, admin: dict) -> Result:
    if admin["role"] not in ("owner", "admin"):
        return Result(False, "⛔ Ruxsat yo'q.")
    try:
        async with get_kv().lock(f"order:{order_id}"):
            o = await get_order(order_id)
            if not o:
                return Result(False, "Buyurtma topilmadi.")
            await get_db().update(ORDERS, "order_id", order_id, {"final_price": price, "updated_at": now_str()})
            await _log(order_id, o["status"], o["status"], admin,
                       f"Yakuniy narx o'zgartirildi: {o['final_price'] or '—'} → {price:g}")
            o["final_price"] = price
            return Result(True, "Yakuniy narx saqlandi.", o)
    except LockBusy as e:
        return Result(False, str(e))


async def complete_delivery_with_payment(
    order_id: str,
    actor: dict,
    method: str,
    cash: float,
    card: float,
    credit: float,
    notes: str = "",
    final_price: float | None = None,
) -> Result:
    """Yetkazib berishni yakunlash + mijoz to'lovini saqlash + kirim yozish.

    method: cash | card | half | credit | mixed
    """
    from services import finance

    emp = await employees.get_actor(int(actor["telegram_id"]), fresh=True)
    if not emp or emp["role"] != "deliverer":
        return Result(False, "⛔ Faqat yetkazib beruvchi haydovchi bajarishi mumkin.")
    tid = str(emp["telegram_id"])
    try:
        async with get_kv().lock(f"order:{order_id}"):
            o = await get_order(order_id)
            if not o:
                return Result(False, "Buyurtma topilmadi.")
            if o["status"] != "delivering":
                return Result(False, "⚠️ Buyurtma holati mos emas (allaqachon yakunlangan bo'lishi mumkin).")
            if str(o.get("delivery_driver_id")) != tid:
                return Result(False, "⛔ Bu buyurtma sizga biriktirilmagan.")

            ts = now_str()
            price = final_price if final_price is not None else (num(o.get("final_price")) or num(o.get("estimated_price")))
            cash = round(max(cash, 0), 2)
            card = round(max(card, 0), 2)
            credit = round(max(credit, 0), 2)
            total_paid = round(cash + card + credit, 2)

            if method == "credit":
                payment_status = "nasiya"
            elif credit > 0 and (cash > 0 or card > 0):
                payment_status = "qisman"
            elif credit > 0:
                payment_status = "nasiya"
            elif total_paid > 0:
                payment_status = "to'langan"
            else:
                payment_status = "to'lanmagan"

            # Komissiya hisoblash (delivery)
            amount = await salaries.record_earning(emp, {**o, "final_price": price}, "delivery")

            updates = {
                "status": "delivered",
                "delivered_at": ts,
                "updated_at": ts,
                "final_price": price,
                "delivery_commission": amount,
                "payment_method": method,
                "payment_cash": cash,
                "payment_card": card,
                "payment_credit": credit,
                "payment_notes": notes or "",
                "payment_status": payment_status,
            }
            if not await get_db().update(ORDERS, "order_id", order_id, updates):
                return Result(False, "Jadvalni yangilab bo'lmadi, qayta urinib ko'ring.")
            o.update(updates)
            await _log(order_id, "delivering", "delivered", emp,
                       f"Mijozga topshirildi. To'lov: {method} "
                       f"(naqd={cash}, karta={card}, nasiya={credit})"
                       + (f". Izoh: {notes}" if notes else ""))

            # Kirim yozuvi
            ok, _ = await finance.record_order_income(
                o, method, cash, card, credit, notes, emp["telegram_id"]
            )
            if not ok:
                # allaqachon bor — e'tiborsiz
                pass
            return Result(True, "✅ Mijozga topshirildi va to'lov saqlandi.", o)
    except LockBusy as e:
        return Result(False, str(e))


# ------------------------------------------------------------------ xodim statistikasi
async def employee_counts(tid) -> dict:
    tid = str(tid)
    c = {"collection": 0, "washing": 0, "finishing": 0, "delivery": 0}
    for o in await get_db().rows(ORDERS):
        c["collection"] += o["collection_driver_id"] == tid and bool(o["collected_at"])
        c["washing"] += o["washing_employee_id"] == tid and bool(o["washing_completed_at"])
        c["finishing"] += o["finishing_employee_id"] == tid and bool(o["finishing_completed_at"])
        c["delivery"] += o["delivery_driver_id"] == tid and bool(o["delivered_at"])
    return c


async def employee_history(tid, limit: int = 15) -> list[dict]:
    rows = [h for h in await get_db().rows(HISTORY) if h["employee_telegram_id"] == str(tid)]
    return sorted(rows, key=lambda h: h["timestamp"], reverse=True)[:limit]


# ------------------------------------------------------------------ biznes statistikasi
async def statistics() -> list[dict]:
    n = now()
    midnight = n.replace(hour=0, minute=0, second=0, microsecond=0)
    periods = [
        ("📅 Bugun", midnight),
        ("🗓 Shu hafta", midnight - timedelta(days=n.weekday())),
        ("📆 Shu oy", midnight.replace(day=1)),
    ]
    db = get_db()
    orders, earns = await db.rows(ORDERS), await db.rows(EARNINGS)
    liabilities = sum(max(b["outstanding"], 0) for b in (await salaries.all_balances()).values())
    out = []
    for label, start in periods:
        s = start.strftime(FMT)

        def inp(ts):
            return bool(ts) and ts >= s

        out.append({
            "label": label,
            "total": sum(inp(o["created_at"]) for o in orders),
            "completed": sum(inp(o["delivered_at"]) for o in orders),
            "pending": sum(inp(o["created_at"]) and o["status"] not in ("delivered", "cancelled") for o in orders),
            "collected": sum(int(num(o["carpet_count"])) for o in orders if inp(o["collected_at"])),
            "washed": sum(int(num(o["carpet_count"])) for o in orders if inp(o["washing_completed_at"])),
            "finished": sum(int(num(o["carpet_count"])) for o in orders if inp(o["finishing_completed_at"])),
            "delivered": sum(int(num(o["carpet_count"])) for o in orders if inp(o["delivered_at"])),
            "sqm": round(sum(num(o["total_area"]) for o in orders if inp(o["washing_completed_at"])), 2),
            "earnings": sum(num(e["amount"]) for e in earns if inp(e["date"])),
            "liabilities": liabilities,
        })
    return out


def status_label(s: str) -> str:
    return STATUS_LABELS.get(s, s)
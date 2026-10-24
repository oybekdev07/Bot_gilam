"""Buyurtma matnini tahlil qilish: ism, telefon, manzil, gilamlar soni, tur va izoh.

Tartib MUHIM EMAS va ajratgich ixtiyoriy: vergul, nuqta-vergul yoki yangi qator.
    Ali Valiyev, 91 123 45 67, Chilonzor 5-kvartal, 12-uy, 3 ta, jun, dog' bor
    91 123 45 67, Chilonzor 5, 3 ta gilam, ipak, Ali Valiyev
Ism: / Tel: / Manzil: / Soni: / Turi: / Izoh: deb yozish ham mumkin.
Xaritadagi havola yoki koordinata (41.31, 69.24) yozilsa, joylashuv sifatida olinadi.
"""
import re
from urllib.parse import unquote

CTYPES = ["Oddiy", "Jun", "Ipak", "Sintetik", "Boshqa"]
CTYPE_ALIASES = {
    "oddiy": "Oddiy", "jun": "Jun", "junli": "Jun", "ipak": "Ipak", "ipakli": "Ipak",
    "sintetik": "Sintetik", "sintetika": "Sintetik", "boshqa": "Boshqa",
}
CTYPE_FILLER = {"gilam", "gilamlar", "mato", "matosi", "turi", "tur", "dona", "ta"}

LABEL_RE = re.compile(r"^\s*(ism|ismi|mijoz|tel|telefon|raqam|nomer|manzil|adres|soni|miqdor|turi|tur|mato|izoh|eslatma)"
                      r"\s*[:=]\s*(.*)$", re.I)
LABEL_MAP = {"ism": "name", "ismi": "name", "mijoz": "name",
             "tel": "phone", "telefon": "phone", "raqam": "phone", "nomer": "phone",
             "manzil": "address", "adres": "address",
             "soni": "count", "miqdor": "count",
             "turi": "ctype", "tur": "ctype", "mato": "ctype",
             "izoh": "instr", "eslatma": "instr"}

PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{6,}\d")
COUNT_RES = (re.compile(r"(?<![\d.,])(\d{1,2})\s*(?:ta|dona)\b(?:\s*gilam(?:lar)?)?", re.I),
             re.compile(r"(?<![\d.,])(\d{1,2})\s*gilam(?:lar)?\b", re.I))
URL_RE = re.compile(r"https?://\S+", re.I)
COORD_RE = re.compile(r"(?<![\d.])(-?\d{1,2}\.\d{3,})\s*[,;/ ]\s*(-?\d{1,3}\.\d{3,})(?!\d)")
LETTERS_RE = re.compile(r"^[^\W\d_]+(?:[\s'.\-]+[^\W\d_]+)*[.'\-]?$", re.U)

ADDR_WORDS = {
    "ko'cha", "kocha", "ko'chasi", "mavze", "mavzesi", "mahalla", "mahallasi", "mfy", "massiv", "massivi",
    "kvartal", "kvartali", "kv", "uy", "uyi", "dom", "tuman", "tumani", "shosse", "prospekt", "ul", "yo'li",
    "tor", "qishloq", "shahar", "metro", "bozor", "orqasida", "yonida", "oldida", "ro'parasida",
    "chilonzor", "yunusobod", "sergeli", "yakkasaroy", "shayxontohur", "shaykhontohur", "olmazor", "uchtepa",
    "mirobod", "yashnobod", "bektemir", "yangihayot", "zangiota", "qibray", "chirchiq", "toshkent", "tashkent",
    "nurafshon", "olmaliq", "angren", "yunusabad", "chilanzar", "mirzo", "ulug'bek", "ulugbek", "qoyliq",
    "yangiyo'l", "bo'ka", "piskent", "ohangaron", "parkent", "samarqand", "buxoro", "andijon", "namangan",
    "farg'ona", "qarshi", "nukus", "xorazm", "urganch", "termiz", "guliston", "jizzax", "navoiy",
}


def norm_phone(text: str):
    """Faqat 9 ta raqam (91 123 45 67) yoki +998 bilan 12 ta raqam qabul qilinadi. Aks holda None."""
    digits = re.sub(r"\D", "", text or "")
    if len(digits) == 12 and digits.startswith("998"):
        digits = digits[3:]
    if len(digits) != 9:
        return None
    return "+998" + digits


def phone_error(raw: str) -> str:
    n = len(re.sub(r"\D", "", raw or ""))
    return (f"Telefon raqami <b>9 ta raqam</b> bo'lishi kerak (masalan <code>91 123 45 67</code>). "
            f"Siz {n} ta raqam kiritdingiz.")


def _apos(s: str) -> str:
    return re.sub(r"[‘’ʻʼ`´]", "'", s)


def _words(s: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", s.lower(), re.U)


def _cut(tok: str, mt) -> str:
    return (tok[:mt.start()] + " " + tok[mt.end():]).strip(" ,-–—.")


def _ctype_of(tok: str):
    """Butun bo'lak faqat mato nomi (va «gilam», «turi» kabi so'zlar) bo'lsa — canonical tur."""
    ws = _words(tok)
    hit = [CTYPE_ALIASES[w] for w in ws if w in CTYPE_ALIASES]
    if hit and all(w in CTYPE_ALIASES or w in CTYPE_FILLER for w in ws):
        return hit[0]
    return None


def _is_addr_like(tok: str) -> bool:
    return bool(re.search(r"\d", tok)) or any(w in ADDR_WORDS for w in _words(tok))


def _name_score(tok: str) -> float:
    ws = tok.split()
    score = 0.0
    if 2 <= len(ws) <= 3:
        score += 3
    elif len(ws) == 1:
        score += 1
    if all(w[:1].isupper() for w in ws):
        score += 1
    if len(ws) > 4:
        score -= 5
    return score


def parse_order_text(text: str):
    """(data, errors) qaytaradi. data: name, phone, address, count, ctype, instr, lat, lon."""
    text = _apos(text or "")
    f: dict = {}
    notes: list[str] = []
    lat = lon = None

    # 1) xarita havolasi va koordinata (vergul bilan bo'linib ketmasligi uchun avval olinadi)
    for url in URL_RE.findall(text):
        mt = COORD_RE.search(unquote(url))
        if mt and lat is None:
            lat, lon = float(mt[1]), float(mt[2])
        elif not mt:
            notes.append(url.rstrip(".,"))
    text = URL_RE.sub(" ", text)
    mt = COORD_RE.search(text)
    if mt and lat is None:
        lat, lon = float(mt[1]), float(mt[2])
        text = text[:mt.start()] + " " + text[mt.end():]
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        lat = lon = None

    # 2) bo'laklarga ajratish: yangi qator, nuqta-vergul, vergul
    addr: list[tuple[int, str]] = []   # (tartib, matn)
    plain: list[tuple[int, str]] = []  # faqat harf: ism / izoh bo'lishi mumkin
    bare: list[tuple[int, str]] = []   # yolg'iz son: gilam soni yoki uy raqami
    idx = 0
    for line in text.split("\n"):
        label = None
        for tok in re.split(r"[;,]+", line):
            tok = tok.strip(" \t-–—")
            if not tok:
                continue
            idx += 1
            lm = LABEL_RE.match(tok)
            if lm:
                label = LABEL_MAP[lm[1].lower()]
                val = lm[2].strip()
                if label == "address":
                    addr.append((idx, val)) if val else None
                elif val:
                    f.setdefault(label, val)
                continue
            if label == "address" and not (PHONE_RE.search(tok) or any(r.search(tok) for r in COUNT_RES)
                                           or _ctype_of(tok)):
                addr.append((idx, tok))  # «Manzil: Chilonzor, 5-kvartal» — davomi
                continue
            if label in ("instr", "name") and not PHONE_RE.search(tok):
                f[label] = f.get(label, "") + (", " if f.get(label) else "") + tok
                continue

            # telefon
            if "phone" not in f:
                pm = PHONE_RE.search(tok)
                if pm and len(re.sub(r"\D", "", pm[0])) >= 7:
                    f["phone"] = pm[0]
                    tok = _cut(tok, pm)
                    if not tok:
                        continue
            # gilamlar soni («3 ta», «3 ta gilam», «3 gilam»)
            if "count" not in f:
                for rx in COUNT_RES:
                    cm = rx.search(tok)
                    if cm:
                        f["count"] = cm[1]
                        tok = _cut(tok, cm)
                        break
                if not tok:
                    continue
            # mato turi
            ct = _ctype_of(tok)
            if ct:
                f.setdefault("ctype", ct)
                continue
            if re.fullmatch(r"\d{1,3}", tok):
                bare.append((idx, tok))
            elif _is_addr_like(tok):
                addr.append((idx, tok))
            elif LETTERS_RE.match(tok):
                plain.append((idx, tok))
            else:
                addr.append((idx, tok))

    # 3) yolg'iz son: aniq «N ta» bo'lmasa — oxirgisi gilam soni, qolganlari manzilga (uy raqami)
    if "count" in f:
        mt = re.search(r"\d+", f["count"])
        f["count"] = mt[0] if mt else f["count"]
        addr += bare
    elif bare:
        f["count"] = bare[-1][1]
        addr += bare[:-1]

    # 4) ism va manzil
    if "name" not in f and plain:
        best = max(range(len(plain)), key=lambda i: (_name_score(plain[i][1]), -i))
        f["name"] = plain.pop(best)[1]
    if "address" in f:
        addr.append((0, f.pop("address")))
    if not addr and plain:
        addr.append(plain.pop(0))
    address = ", ".join(t for _, t in sorted(addr, key=lambda x: x[0]))
    instr = ", ".join(x for x in [f.get("instr", ""), *[t for _, t in plain], *notes] if x)

    ctype = f.get("ctype", "")
    ctype = CTYPE_ALIASES.get(ctype.lower(), ctype) if ctype else ""

    # 5) tekshiruv
    errors = []
    name = (f.get("name") or "").strip()
    if not 2 <= len(name) <= 80:
        errors.append("Mijoz ismi topilmadi (2–80 belgi, raqamsiz).")
    phone = norm_phone(f.get("phone", ""))
    if not f.get("phone"):
        errors.append("Telefon raqami topilmadi.")
    elif not phone:
        errors.append(phone_error(f["phone"]))
    address = address.strip()
    if not 5 <= len(address) <= 300:
        errors.append("Manzil topilmadi yoki juda qisqa (kamida 5 belgi).")
    count = int(f["count"]) if str(f.get("count", "")).isdigit() else 0
    if not 1 <= count <= 30:
        errors.append("Gilamlar soni topilmadi (1 dan 30 gacha, masalan <code>3 ta</code>).")
    data = {"name": name, "phone": phone, "address": address, "count": count,
            "ctype": ctype, "instr": instr[:500], "lat": lat, "lon": lon}
    return data, errors

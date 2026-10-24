# 🧺 Gilam yuvish boti (faqat Telegram)

## 🗄 Baza: SQLite (yangi)

Barcha ma'lumotlar endi **`data/carpet.db`** (SQLite) faylida saqlanadi — internet va Google API limitlariga bog'liq emas, tez ishlaydi.
Google Sheets esa **faqat hisobot/ko'rish uchun**: botda administrator **📤 Google Sheetga** tugmasini bosadi — bazadagi hamma narsa
(Orders, Customers, Employees, Employee Earnings, Salary Payments, Order History, Settings) jadvalga yoziladi.
Tugmani qayta bossangiz dublikat bo'lmaydi: varaqlar bazadagi holat bilan to'liq almashtiriladi.

- `.env` da `GOOGLE_SHEET_ID` va `GOOGLE_SERVICE_ACCOUNT_FILE` bo'lsa tugma ishlaydi (jadval service account emailiga **Editor** qilib ulashilgan bo'lishi kerak). Bo'sh bo'lsa ham bot to'liq ishlaydi.
- Eski Google Sheets ma'lumotlarini bir marta bazaga ko'chirish: `python migrate_from_sheets.py`
- **Zaxira nusxa:** `data/carpet.db` faylini vaqti-vaqti bilan nusxalab qo'ying (bot to'xtatilgan paytda).
- ⚠️ SQLite fayl lokal kompyuterda ishlaydi. **Vercel (webhook) rejimi endi to'g'ri ishlamaydi** — Vercel'da fayl doimiy saqlanmaydi. Bot `python run_local.py` bilan ishlaydi.

## 🧾 Yangi buyurtma — bitta xabar, vergul bilan, tartib muhim emas

```
Ali Valiyev, 91 123 45 67, Chilonzor 5-kvartal 12-uy, 3 ta, jun, dog' bor
91 123 45 67, Chilonzor 5-kvartal 12-uy, 3 ta gilam, ipak, Ali Valiyev
```
Bot ismni, telefonni, manzilni, gilamlar sonini (`3 ta`), mato turini (Oddiy/Jun/Ipak/Sintetik) va izohni o'zi taniydi.
Xarita havolasi yoki koordinata (`41.31, 69.24`) yozilsa — joylashuv sifatida saqlanadi. Noto'g'ri tanilgan bo'lsa, tasdiqlash
oynasida **🔁 Ism ↔ Manzil almashtirish** yoki **✏️ Qayta yozish** tugmasi bor.

---

Butun biznes Telegram ichida boshqariladi. Veb-sayt yo'q. Ma'lumotlar **Google Sheets**'da saqlanadi.
Texnologiya: Python 3.12, aiogram 3, Google Sheets API, Vercel (webhook), Upstash Redis.

> ⚠️ **Maxfiylik:** bot tokenni hech kimga, hech qaysi chatga yubormang (menga ham). Token faqat Vercel'dagi
> *Environment Variables* bo'limiga kiritiladi. Agar token tasodifan oshkor bo'lsa — @BotFather → `/revoke`.

## 💻 VS Code'da lokal ishga tushirish (tavsiya etiladi)

Vercel ham, Redis ham, webhook ham kerak emas — bot kompyuteringizda **long polling** bilan ishlaydi.

1. VS Code'da papkani oching: **File → Open Folder → carpet-bot**.
2. Python 3.12+ o'rnatilgan bo'lishi kerak. Terminalda (**Ctrl+`**):
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   (yoki `setup.bat` ni ikki marta bosing)
3. `.env` faylini tekshiring (BOT_TOKEN, ADMIN_IDS, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE).
4. Jadvalni service account `client_email` manziliga **Editor** sifatida ulashing (4–5-qadamlar yuqorida).
5. Ishga tushirish: **F5** (Botni ishga tushirish) yoki terminalda `python run_local.py` (yoki `run.bat`).
6. To'xtatish: **Ctrl+C**.

Testlar: **Run and Debug** panelidan "Test: to'liq oqim" yoki `python tests/test_flow.py`.

> ⚠️ Bot bir vaqtning o'zida faqat **bitta** joyda ishlashi kerak: lokal polling ishga tushganda Vercel webhook'i o'chiriladi.
> Keyin Vercel'ga qaytmoqchi bo'lsangiz, `…/webhook?setup=1` ni qayta oching.
> Lokal rejimda FSM holati xotirada saqlanadi: bot qayta ishga tushsa, jarayondagi bosqichlar uchun `/start` bosish kerak
> (buyurtmalar va boshqa ma'lumotlar Google Sheets'da qoladi).

---

## Nega Redis (Upstash) kerak? (faqat Vercel uchun)
Vercel serverless — har so'rov alohida ishga tushadi, xotira saqlanmaydi. Redis quyidagilar uchun kerak:
1. **FSM holati** (buyurtma kiritish bosqichlari) so'rovlar orasida yo'qolmasligi uchun;
2. **Ikki haydovchi bitta buyurtmani olmasligi** uchun qulf (Google Sheets'da atomik qulf yo'q);
3. Telegram **webhook takrorlanishi** (update_id) dublikat yaratmasligi uchun.

Redis faqat vaqtinchalik holat saqlaydi. Barcha biznes ma'lumotlar baribir Google Sheets'da. Bepul tarif yetarli.

## O'rnatish (10 qadam)

### 1. Telegram bot yaratish
Telegram'da **@BotFather** → `/newbot` → nom va `...bot` bilan tugaydigan username bering → u sizga **token** beradi
(`123456:ABC...`). Uni hozircha boshqa joyga ko'chirib qo'ying (yubormang).

### 2. O'z Telegram ID raqamingizni bilish
Telegram'da **@userinfobot** ga `/start` yuboring — u `Id: 123456789` deb javob beradi. Shu raqam `ADMIN_IDS` bo'ladi.

### 3. Google Sheet yaratish
[sheets.google.com](https://sheets.google.com) → bo'sh jadval yarating. Havoladagi uzun qismni nusxalang:
`docs.google.com/spreadsheets/d/`**`SHU_QISM`**`/edit` → bu `GOOGLE_SHEET_ID`.
Varaqlarni qo'lda yaratish shart emas — bot o'zi yaratadi.

### 4. Google Cloud service account
1. [console.cloud.google.com](https://console.cloud.google.com) → yangi loyiha yarating.
2. **APIs & Services → Library** → "Google Sheets API" → **Enable**.
3. **APIs & Services → Credentials → Create credentials → Service account** → nom bering → Done.
4. Yaratilgan service account → **Keys → Add key → Create new key → JSON** → fayl yuklab olinadi.
   Faylni Notepad'da oching — **butun matn** `GOOGLE_SERVICE_ACCOUNT_JSON` qiymati bo'ladi.
5. Shu JSON ichidagi `client_email` (…@…iam.gserviceaccount.com) manzilini nusxalang.

### 5. Jadvalni service account bilan ulashish
Google Sheet'da **Share** → `client_email` manzilini kiriting → huquq: **Editor** → Send.

### 6. GitHub'ga yuklash va Vercel'ga ulash
1. [github.com](https://github.com) → **New repository** (Private tavsiya) → loyiha fayllarini yuklang.
   (`.env` faylini yuklamang; `.gitignore` buni oldini oladi.)
2. [vercel.com](https://vercel.com) → **Add New → Project** → GitHub repozitoriyni **Import** → hali **Deploy** bosmang.

### 7. Environment Variables (Vercel'da)
Import oynasida **Environment Variables** bo'limi bor (keyin: Project → **Settings → Environment Variables**).
Quyidagilarni bittadan kiriting:

| Nomi | Qiymati |
|---|---|
| `BOT_TOKEN` | @BotFather bergan token |
| `ADMIN_IDS` | Sizning Telegram ID (bir nechta bo'lsa: `111,222`) |
| `GOOGLE_SHEET_ID` | 3-qadamdagi ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON faylning butun matni |
| `WEBHOOK_SECRET` | O'zingiz o'ylab topgan uzun so'z, 20+ belgi (faqat lotin harf, raqam, `_`, `-`) |
| `TIMEZONE` | `Asia/Tashkent` |

**Redis:** Vercel loyihangizda **Storage** (yoki Marketplace) → **Upstash Redis** (yoki "KV") → Create → loyihaga **Connect**.
`KV_REST_API_URL` va `KV_REST_API_TOKEN` avtomatik qo'shiladi.

### 8. Deploy
**Deploy** tugmasini bosing (o'zgaruvchilarni keyin qo'shsangiz — **Deployments → … → Redeploy**).

*Buyruq qatori orqali (ixtiyoriy):*
```
npm i -g vercel
vercel login
vercel link
vercel --prod
```

### 9. Webhook'ni ro'yxatdan o'tkazish
Brauzerda oching (o'z domeningiz bilan):
```
https://SIZNING-LOYIHA.vercel.app/webhook?setup=1
```
U webhook'ni o'rnatadi va Google Sheets ulanishini tekshiradi. Javobda ✅ belgilari chiqishi kerak.
Agar ❌ chiqsa, xabar sababini ko'rsatadi (masalan: jadval ulashilmagan, token xato).
Domen avtomatik aniqlanmasa — `PUBLIC_URL` o'zgaruvchisini kiriting (`https://…vercel.app`).

### 10. Sinash
Botga `/start` yuboring. Siz **Ega** sifatida admin menyuni ko'rasiz. Keyin:
**👥 Xodimlar → ➕ Xodim qo'shish** orqali boshqa Telegram akkauntlarni qo'shing (operator, haydovchi, yuvuvchi,
pardozlovchi, yetkazuvchi). Xodim botga `/start` bosib o'z ID raqamini ko'radi.

## Rollar
- **Ega** (`ADMIN_IDS`): hamma narsa, administrator tayinlash.
- **Administrator:** xodimlar, ish haqi, sozlamalar, buyurtmalarni biriktirish; yangi buyurtma ham kirita oladi.
- **Operator, Olib ketuvchi, Yuvuvchi, Pardozlovchi, Yetkazuvchi:** faqat o'z menyusi.

Foydalanuvchi **Telegram ID** bo'yicha aniqlanadi; tugma ma'lumotini o'zgartirish yoki rol nomini yozish ruxsat bermaydi.
Xodim o'chirilsa (🔴), keyingi amalida rad etiladi.

## Ish haqi qoidalari
- **Komissiya** (Sozlamalar'da): har vazifa uchun tur — *narxdan foiz*, *1 m² uchun* yoki *qat'iy summa*. Xodimga maxsus qiymat berish mumkin.
- Vazifa tugaganda daromad **bir marta** yoziladi (`E-<buyurtma>-<vazifa>`).
- **Qat'iy oylik:** administrator "📅 Oylikni hisoblash" bosadi — shu oy uchun bir marta daromadga qo'shiladi.
- **Qoldiq = jami daromad − jami to'lovlar.** Qisman va to'liq to'lov mumkin; qoldiqdan ortiq to'lab bo'lmaydi.
- Daromadlar (`Employee Earnings`) va to'lovlar (`Salary Payments`) alohida varaqlarda — ikki marta sanalmaydi.

## Google Sheets varaqlari
`Orders`, `Customers`, `Employees`, `Employee Earnings`, `Salary Payments`, `Order History`, `Settings`.
Sarlavhalarni o'chirmang va ustun nomlarini o'zgartirmang. Ma'lumotni qo'lda tahrirlash mumkin, lekin xodim qo'shish/o'chirishni botdan qiling.

## Cheklovlar (halol eslatma)
- Google Sheets API: ~60 o'qish/daqiqa. Kichik va o'rta biznes uchun yetarli; juda katta oqimda "band" xabari chiqishi mumkin (bot qayta urinadi).
- Xodim o'chirilgandan keyin ro'yxat keshi tufayli ≤10 soniya kechikish bo'lishi mumkin (bosqich amallarida esa tekshiruv har safar yangidan).
- Redis ulanmasa bot lokal rejimda ishlaydi, lekin **Vercel'da ishonchli emas**.
- Telegram foydalanuvchi botni bloklagan bo'lsa, unga xabar yetmaydi — administratorga ogohlantirish boradi.

## Lokal sinov (ixtiyoriy)
```
pip install -r requirements.txt
python3 tests/test_flow.py            # to'liq oqim (soxta Telegram + xotiradagi jadval)
python3 tests/test_webhook_redis.py   # webhook va Redis qatlami
```


## Yangi: mijoz toʻlovi, kirim/chiqim, davriy oylik (v2)

### Yetkazib berishda toʻlov
Haydovchi «Mijozga topshirildi» ni bosganda avval **toʻlov usuli** soʻraladi:
- 💵 Toʻliq naqd
- 💳 Toʻliq karta
- 💵💳 Yarim naqd / yarim karta
- 📝 Nasiya (qarz)
- 🔀 Aralash (naqd + karta + nasiya, izoh bilan)

Summalar buyurtmada ( ustunlari) va **Income** jadvalida saqlanadi.

### Kirim / Chiqim (admin menyu)
- **Kirim** — mijoz toʻlovlari (yetkazish yakunida avtomatik)
- **Chiqim** — xodim oyligi (toʻlov qilinganda avtomatik) + qoʻlda: yoqilgʻi, moy, ovqat, taʼmirlash, ijara, boshqa
- Bugun / hafta / oy / yil boʻyicha jami kirim, chiqim va foyda

### Xodim oyligi
- Bir gilamni **bitta** yuvuvchi oladi (claim)
- Komissiya ish bajarilgan paytdagi stavka boʻyicha hisoblanadi (stavka oshsa — yangi ishlarga yangi stavka)
- Xodim kartasida: **shu hafta / oy / yil** hisoblangan daromad
- Stavkani oʻzgartirish: Xodimlar → xodim → maxsus komissiya yoki Sozlamalar (umumiy 1 m² narxi)
#   B o t _ g i l a m  
 
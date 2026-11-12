# BloodNet — قرارداد مشترک تیم (Single Source of Truth)

> **وضعیت: FROZEN (نسخه 1.0)** — این سند پیش از شروع هر کدنویسی توسط کل تیم تأیید شده است.
> هر نام فیلد، مقدار enum، مسیر endpoint، نام جدول، نام تابع و کلید تنظیمات در این سند **قطعی** است.
> هیچ عضوی حق تغییر یا ابداع نام جدید خارج از این سند را ندارد. اگر چیزی کم است، ابتدا در جلسه تیم مطرح و اینجا ثبت میشود، سپس کد نوشته میشود.
> قانون طلایی: **تمام کد، شناسهها، مقادیر، پیامهای commit و نام branchها انگلیسی هستند.** فقط متنهای داخل رابط کاربری فارسی است.

---

## ۱. تصویر کلی پروژه

**BloodNet** — سرویس هماهنگی زنجیره تأمین خون یک استان ساختگی. بیمارستانها درخواست خون میدهند، سرویس ما موجودی مراکز را (با رعایت سازگاری و انقضا) تخصیص میدهد، برای کسری، اهداکنندگان واجد شرایط را از طریق Gateway شبیهسازیشده دعوت میکند و پاسخها را تا تکمیل تأمین پردازش میکند.

- معماری: **Modular Monolith + Layered (API → Service → Domain → Data) + Hexagonal-lite** برای ۴ سرویس کیت.
- استک: **Python 3.10+ / FastAPI / Pydantic v2 / SQLAlchemy 2 (async) + SQLite (WAL) / Vanilla JS (بدون build) / scikit-learn (ماژول هوشمند) / pytest / httpx**.
- سرویس ما روی `:8000`؛ سرویسهای کیت: Gateway `:9100`، Travel `:9200`، Inventory `:9300`.
- ساعت رسمی فقط از `GET /clock` میآید؛ استفاده از ساعت سیستم **ممنوع**.

---

## ۲. قرارداد رسمی API سرویس ما (openapi.yaml کیت — عیناً پیادهسازی میشود)

### ۲.۱ مسیرها (paths)

| Method | Path | Auth | Body/Params | پاسخهای موفق | خطاها |
|---|---|---|---|---|---|
| GET | `/health` | ندارد | — | `200 {"ok": true}` | — |
| POST | `/requests` | `hospitalBearer` | `NewRequest` + هدر اجباری `Idempotency-Key` (1..128 کاراکتر) + هدر اختیاری `X-Sim-Time` (number) | `201` / `200` (replay) | `400` `401` `422` `429` `503` |
| GET | `/requests/{id}` | `hospitalBearer` | — | `200 RequestState` | `401` `404` |
| POST | `/requests/{id}/cancel` | `hospitalBearer` | body خالی `{}` | `200` (تکرار = no-op) | `401` `404` |
| POST | `/requests/{id}/approve` | `coordinatorBearer` | `Approval` (اختیاری) | `200` | `401` `404` `409` |
| POST | `/requests/{id}/amend` | `hospitalBearer` | `AmendRequest` | `200` | `401` `404` `409` |
| POST | `/callbacks/donor-response` | ندارد | `DonorResponseCallback` | `200` | `400` |
| POST | `/callbacks/donor-progress` | ندارد | `DonorProgressCallback` | `200` | `400` |
| POST | `/callbacks/gateway-status` | ندارد | `GatewayStatusCallback` | `200` | `400` |

نکات قطعی:
- پاسخ `GET /requests/{id}` باید حداقل شامل `request_id, status, needed, confirmed, en_route, arrived, fulfilled` باشد. فیلدهای اضافه مجاز است (تست قرارداد فقط فیلدهای اجباری را چک میکند).
- callback تکراری با همان `event_id` → همیشه `200` و فقط یکبار شمارش.
- callback با `request_id` ناشناخته → `200` و نادیده گرفتن (بدون خطا).
- بدنه JSON خراب/خالی → `400`.

### ۲.۲ Schemaهای رسمی (نام فیلدها قطعی است)

```yaml
NewRequest:
  hospital_id: string            # مثال H07
  blood_group: enum [O+, A+, B+, AB+, O-, A-, B-, AB-]
  product:     enum [red_cells, platelets, plasma]
  units:       integer 1..20
  urgency:     enum [critical, urgent, planned]
  note:        string ≤500 (اختیاری)
  # additionalProperties: false — هر فیلد اضافه → 400

RequestStatus: enum [pending_review, open, mobilizing, partially_fulfilled, fulfilled, cancelled, expired]

RequestState:
  request_id: string
  status:     RequestStatus
  needed:     integer ≥1
  confirmed:  integer ≥0
  en_route:   integer ≥0
  arrived:    integer ≥0
  fulfilled:  integer ≥0

AmendRequest:  { urgency: enum [critical, urgent, planned] }
Approval:      { approved: boolean (پیشفرض true), note: string }   # کل body اختیاری

DonorResponseCallback:
  event_id: string (اجباری) | request_id: string | donor_id: string
  notification_id: string | response: enum [accepted, declined]
  reason: string (اختیاری، مثل not_eligible یا busy) | sim_time: number

DonorProgressCallback:
  event_id: string | request_id: string | donor_id: string
  event: enum [en_route, arrived, screen_pass, screen_fail, donated, no_show]
  reason: string (اختیاری) | sim_time: number

GatewayStatusCallback:
  event_id: string | notification_id: string | request_id: string | donor_id: string
  status: enum [queued, sent, delivered, failed, expired] | sim_time: number
```

### ۲.۳ قالب خطا (برای تمام پاسخهای خطای سرویس ما)

```json
{ "error": { "code": "string", "message": "string" } }
```

کدهای خطای قطعی:

| code | کاربرد |
|---|---|
| `unauthorized` | توکن غایب/نامعتبر (401) |
| `not_found` | request_id ناشناخته (404) |
| `missing_idempotency_key` | POST /requests بدون هدر Idempotency-Key (400) |
| `idempotency_key_reuse` | کلید تکراری با بدنه متفاوت (422) — **این کد دقیق در تست قرارداد چک میشود** |
| `validation_error` | بدنه/مقدار نامعتبر (400) |
| `unknown_hospital` | hospital_id ثبتنشده (مثل H98) (400) |
| `not_amendable` | اصلاح در وضعیت غیرمجاز (409) |
| `not_approvable` | تأیید در وضعیت غیر از pending_review (409) |
| `internal_error` | خطای غیرمنتظره (500) |

---

## ۳. قرارداد سرویسهای کیت (ما کلاینت آنها هستیم)

### ۳.۱ Gateway (`GATEWAY_URL` = http://localhost:9100)

| Method | Path | Body/Query | پاسخ |
|---|---|---|---|
| GET | `/health` | — | `{ok, sim_time, mode}` |
| GET | `/clock` | — | `{sim_time: number, epoch: "2027-01-15T00:00:00+03:30", speed: number}` |
| POST | `/messages` | `{notification_id, donor_id, template, request_id, callback_url}` | `202` پذیرفته شد؛ `409` notification_id تکراری؛ `429`/`503` با هدر `Retry-After` |

- `template` ∈ `[request_wave, confirmed, not_needed, cancelled, reminder]` — **قطعاً همین ۵ مقدار.**
- Gateway خودش به `callback_url` سه پسوند `/callbacks/gateway-status`، `/callbacks/donor-response`، `/callbacks/donor-progress` را اضافه میکند؛ پس `callback_url = SELF_URL` (بدون پسوند).
- هرگز endpoint های `/admin/*` صدا زده نشوند.

### ۳.۲ Travel (`TRAVEL_URL` = http://localhost:9200)

- `GET /travel?from=lat,lon&to=lat,lon` → `{"minutes": number}` (ممکن است 429 بدهد → retry محدود)

### ۳.۳ Inventory (`INVENTORY_URL` = http://localhost:9300)

- `GET /health` → `{"ok": true}`
- `GET /inventory` → `{"sim_time": number, "items": [{"center_id", "blood_group", "product", "units", "expires_at", "expires_sim_min"}]}`
- `POST /inventory/dispatch` — body:

```json
{ "dispatch_id": "...", "request_id": "...", "center_id": "MC1",
  "blood_group": "O-", "product": "red_cells", "units": 1,
  "hospital_id": "H07", "recipient_blood_group": "O+" }
```

پاسخها: `201` ساخته شد / `200` replay با همان dispatch_id / `400` نامعتبر / `404` درخواست ناشناخته / `409` موجودی ناکافی یا درخواست لغوشده / `422` ناسازگاری گروه خون یا محصول یا dispatch_id تکراری با بدنه متفاوت.

- موجودی، اتمی و به ترتیب نزدیکترین انقضا کسر میشود. dispatch ناموفق نباید موجودی ما را تغییر دهد.
- زمان تحویل = ۱۰ دقیقه شبیهسازی + سفر مرکز→بیمارستان. نیمهشب شبیهسازی restock میشود.

---

## ۴. دادههای کیت (فقطخواندنی — نام ستونها قطعی)

| فایل | ستونها |
|---|---|
| `participant_kit/donors.csv` | `donor_id, blood_group, sex, age, weight_kg, lat, lon, area_id, quiet_start_hour, quiet_end_hour, last_donation_at, last_donation_type, permanently_excluded, notified_90d` |
| `participant_kit/hospitals.csv` | `hospital_id, name, lat, lon, request_weight, credit_level` |
| `participant_kit/centers.csv` | `center_id, name, lat, lon, beds, open_hour, close_hour` |
| `participant_kit/inventory.csv` | `center_id, blood_group, product, units, expires_at` (فقط تصویر آغازین) |
| `participant_kit/areas.csv` | `area_id, lat, lon` |
| `participant_kit/donor_events.csv` | `donor_id, event, event_at, defer_days, defer_until` — event ∈ `tattoo` (180 روز) و `travel_risk` (90 روز)؛ رویداد جدیدتر جایگزین قبلی میشود |
| `participant_kit/history/requests.csv` | `rid, created_at, hospital_id, blood_group, product, units, urgency, fulfilled_min, sla_met` |
| `participant_kit/history/responses.csv` | `request_id, donor_id, notified_at, wave, responded, accepted, response_delay_min, arrived, donated` |
| `participant_kit/travel_matrix_areas.csv` | ستون اول `area_id` + ۲۰۰ ستون مقصد (`A000`..`A199`) |
| `participant_kit/travel_area_to_center.csv` | `area_id` + `MC1..MC5` |
| `participant_kit/travel_area_to_hospital.csv` | `area_id` + `H01..H14` |
| `participant_kit/travel_center_to_hospital.csv` | `center_id` + `H01..H14` |
| `participant_kit/compat.yaml` | ماتریس سازگاری: `compat[product][recipient_group] = [donor_groups...]` |
| `participant_kit/rules.yaml` | قواعد زیر (کلیدها قطعی) |

`rules.yaml`:

```yaml
age_min: 18 | age_max: 65 | weight_min_kg: 50
interval_wb_male: 60 | interval_wb_female: 90 | interval_apheresis: 14 | cross_block: 14
event_deferral: {tattoo: 180, travel_risk: 90}
sla: {critical: 90, urgent: 240, planned: 1440}        # دقیقه شبیهسازی
shelf_days: {red_cells: 42, platelets: 5, plasma: 365}
proc_min: 20 | visit_min: {red_cells: 20, platelets: 90, plasma: 45}
```

- سن ۱۸–۶۵، وزن ≥ ۵۰kg، فاصله اهدا: red_cells → 60 (مرد)/90 (زن)، platelets → 14، plasma → 14، نوع متفاوت از قبلی → cross_block=14.
- `quiet_start_hour == quiet_end_hour` یعنی بدون بازه سکوت؛ `start > end` یعنی از نیمهشب عبور میکند.
- `notified_90d`: تعداد اعلانهای ۹۰ روز اخیر (از history محاسبه شده).
- epoch ثابت: `2027-01-15T00:00:00+03:30`.

---

## ۵. قواعد قطعی دامنه (تصمیمات تیم — هر سه عضو باید همین را بدانند)

### ۵.۱ سیاست pending_review (ضد تقلب F14)

- `hospital_id` در hospitals.csv نباشد → **همان لحظه 400 با کد `unknown_hospital`**؛ هیچ موجودی و هیچ موجی مصرف نمیشود.
- بیمارستان ثبتشده: اگر `units ≥ SUSPICIOUS_UNITS_THRESHOLD` یا مجموع units همان بیمارستان در `BURST_WINDOW_MIN` دقیقه اخیر `> BURST_MAX_UNITS` باشد → درخواست در `pending_review` میماند (بدون هیچ هزینهای) تا هماهنگکننده با `/approve` تأیید یا رد کند (`approved: false` → 409 یا ابطال داخلی: تصمیم قطعی = اگر `approved:false` → درخواست `cancelled` با پیام مناسب و پاسخ 200).
- در غیر این صورت → بلافاصله `open` و چرخه تخصیص/دعوت آغاز میشود.

### ۵.۲ ماشین وضعیت (قطعی)

```
            approve(هماهنگکننده) یا auto-open
pending_review ───────────────────────────────► open
open ──(اولین موج دعوت)──► mobilizing
open / mobilizing ──(اولین واحد تأمین: donated یا تحویل موجودی)──► partially_fulfilled
open / mobilizing / partially_fulfilled ──(fulfilled ≥ needed)──► fulfilled
open / mobilizing / partially_fulfilled ──(cancel)──► cancelled
open / mobilizing / partially_fulfilled ──(گذشتن از sla_deadline_sim_min)──► expired
```

- `amend` فقط در `{open, mobilizing, partially_fulfilled}` مجاز است (وگرنه 409 با `not_amendable`). اصلاح فوریت، `sla_deadline_sim_min = now + sla[new_urgency]` را از نو تنظیم میکند.
- `cancel` روی وضعیت پایانی → 200 no-op. لغو یا انقضا → ارسال `cancelled` به دعوتشدگانِ پذیرفته که هنوز اهدا نکردهاند.
- `fulfilled` → ارسال `not_needed` به همان گروه.

### ۵.۳ شمارندهها (صداقت S6 — قطعی)

- `confirmed`: بهازای هر `donor-response: accepted` برای این درخواست، **حداکثر یکبار بهازای هر donor_id** (نگهبان: اگر همین donor قبلاً accepted داشته، دوباره نشمار).
- `en_route` و `arrived`: مشابه — هر event حداکثر یکبار بهازای هر `(request_id, donor_id)`.
- `fulfilled`: فقط از دو منبع — event `donated` (هر donor یکبار) و تحویل dispatch موجودی (زمانی که `delivery_sim_min` فرا رسید).
- `screen_pass`, `screen_fail`, `no_show`: در شمارندهها اثری ندارند؛ فقط ثبت میشوند.
- `stock_inflight`: مجموع units دیسپچهایی که ساخته شده ولی هنوز `delivery_sim_min`شان نرسیده.
- `shortage = max(0, needed - fulfilled - stock_inflight)` — عددی که UI نمایش میدهد.
- **قانون صادقانه:** شمارندهها همیشه واقعیت را نشان میدهند؛ حتی اگر donated دیر برسد و باعث overfill شود، شمارش میشود (کنترل overfill با توقف بهموقع دعوتهاست، نه با سانسور شمارندهها).

### ۵.۴ تخصیص موجودی (F4 — قطعی)

1. `GET /inventory` → فیلتر: `product` یکسان، `expires_sim_min > now`، سازگار (`compat[product][recipient_blood_group]` شامل `blood_group` آیتم).
2. مرتبسازی FEFO (صعودی `expires_sim_min`).
3. برداشت حریصانه تا پوشش `need = needed - fulfilled - stock_inflight`.
4. بهازای هر `(center_id, blood_group)` یک `POST /inventory/dispatch` با `dispatch_id = "dsp-" + uuid4().hex`.
5. پاسخ `201`/`200` → ثبت در جدول `dispatches` با `outcome=created` و `delivery_sim_min = now + 10 + travel(center→hospital)` و `stock_inflight += units`.
6. پاسخ `409/422/400` → ثبت `outcome=failed` (بدون تغییر موجودی محلی) و ادامه با گزینه بعدی.
7. dispatch تکراری با همان `dispatch_id` → 200 idempotent.
8. تلاش مجدد تخصیص بهصورت دورهای برای درخواستهای باز دارای shortage (پوشش restock نیمهشب).

### ۵.۵ دعوت اهداکننده (F6/F12/S2 — قطعی و ایمنی-بحرانی)

**پیشفیلتر واجدین (قبل از هر ارسال؛ تخلف = صفر شدن کل امتیاز):**

| # | شرط | منبع |
|---|---|---|
| 1 | `permanently_excluded == 0` | donors.csv |
| 2 | `18 ≤ age ≤ 65` و `weight_kg ≥ 50` | donors.csv + rules |
| 3 | آخرین `donor_events` (رویداد جدیدتر جایگزین قبلی): اگر `defer_until` تنظیم شده و `now > defer_until` برحسب دقیقه شبیهسازی نگذشته باشد → حذف | donor_events.csv |
| 4 | فاصله اهدا رعایت شده (بخش ۴) | donors.csv + rules |
| 5 | خارج از بازه سکوت (محاسبه ساعت محلی = `(epoch + sim_time دقیقه)` mod 24) | donors.csv |
| 6 | سازگاری گروه خون با recipient | compat.yaml |
| 7 | قبلاً برای همین request_id دعوت نشده | جدول notifications |

**ساخت موج:**
- رتبهبندی: استراتژی از `RANKING_STRATEGY` (پیشفرض `travel_time`: صعودی زمان سفر ناحیه اهداکننده → بیمارستان از `travel_area_to_hospital.csv`، تساویشکن: صعودی `notified_90d`؛ یا `ai_response`: نمره مدل، تساویشکن: زمان سفر).
- سقف موج: `cap = min(max(shortage × WAVE_SIZE_FACTOR, WAVE_MIN_SIZE), WAVE_MAX_SIZE)`.
- ارسال `request_wave` با `notification_id = "nt-" + uuid4().hex` و `callback_url = SELF_URL`.
- موج بعدی: `WAVE_INTERVAL_MIN` دقیقه بعد، حداکثر `WAVE_MAX_COUNT` موج؛ سپس در صورت نیاز فقط `reminder` به پذیرفتههای نیامده (هر `REMINDER_INTERVAL_MIN`).
- پس از `fulfilled/cancelled/expired` → توقف فوری موجها + `not_needed`/`cancelled` به پذیرفتههای بدون اهدا.

**پردازش پاسخها:**
- `accepted` → `confirmed += 1` + ارسال قالب `confirmed`.
- `declined` → فقط ثبت (با reason).
- `donated` → `fulfilled += 1`؛ اگر `fulfilled ≥ needed` → وضعیت `fulfilled` + توقف دعوتها.

---

## ۶. تنظیمات و متغیرهای محیطی (کلیدها قطعی — `.env`)

```ini
PORT=8000
SELF_URL=http://localhost:8000
GATEWAY_URL=http://localhost:9100
TRAVEL_URL=http://localhost:9200
INVENTORY_URL=http://localhost:9300
HOSPITAL_TOKEN=hospital-token
COORDINATOR_TOKEN=coordinator-token
KIT_PATH=./participant_kit
DATABASE_URL=sqlite+aiosqlite:///./bloodnet.db
LOG_LEVEL=INFO
CLOCK_CACHE_TTL_SEC=0.5
HTTP_TIMEOUT_SEC=8
HTTP_MAX_RETRIES=3
DISPATCHER_TICK_SEC=1.0
WAVE_MAX_SIZE=80
WAVE_MIN_SIZE=24
WAVE_SIZE_FACTOR=6
WAVE_INTERVAL_MIN=45
WAVE_MAX_COUNT=4
REMINDER_INTERVAL_MIN=30
PENDING_POLICY=burst_hold
SUSPICIOUS_UNITS_THRESHOLD=15
BURST_WINDOW_MIN=15
BURST_MAX_UNITS=30
ALLOC_RETRY_INTERVAL_MIN=20
RANKING_STRATEGY=travel_time
AI_MODEL_PATH=./app/ai/model/ranker.joblib
DISABLE_OUTREACH=false
```

`.env` هرگز commit نمیشود؛ `.env.example` با همین کلیدها و مقادیر دمو commit میشود.

---

## ۷. پایگاه داده — اسکیما (نام جداول و ستونها قطعی)

موتور: SQLite با WAL (`PRAGMA journal_mode=WAL`، `busy_timeout=10000`، `foreign_keys=ON`). ساخت با `metadata.create_all` در startup (بدون Alembic — الگوی «شروع تازه»).

### `requests`
| ستون | نوع | قید |
|---|---|---|
| `id` | TEXT | PK (فرمت `R-` + 12 hex) |
| `hospital_id` | TEXT | NOT NULL, INDEX |
| `blood_group` | TEXT | NOT NULL |
| `product` | TEXT | NOT NULL |
| `units` | INTEGER | NOT NULL |
| `urgency` | TEXT | NOT NULL |
| `note` | TEXT | NULL |
| `status` | TEXT | NOT NULL |
| `needed` | INTEGER | NOT NULL |
| `confirmed` | INTEGER | NOT NULL DEFAULT 0 |
| `en_route` | INTEGER | NOT NULL DEFAULT 0 |
| `arrived` | INTEGER | NOT NULL DEFAULT 0 |
| `fulfilled` | INTEGER | NOT NULL DEFAULT 0 |
| `stock_inflight` | INTEGER | NOT NULL DEFAULT 0 |
| `idempotency_key` | TEXT | NOT NULL UNIQUE |
| `idempotency_body_hash` | TEXT | NOT NULL |
| `created_sim_min` | REAL | NOT NULL |
| `updated_sim_min` | REAL | NOT NULL |
| `sla_deadline_sim_min` | REAL | NOT NULL |
| `wave_count` | INTEGER | NOT NULL DEFAULT 0 |
| `last_wave_sim_min` | REAL | NULL |

### `dispatches`
`dispatch_id` TEXT PK · `request_id` TEXT NOT NULL INDEX · `center_id` TEXT NOT NULL · `blood_group` TEXT NOT NULL · `product` TEXT NOT NULL · `units` INTEGER NOT NULL · `hospital_id` TEXT NOT NULL · `recipient_blood_group` TEXT NOT NULL · `created_sim_min` REAL NOT NULL · `delivery_sim_min` REAL NOT NULL · `outcome` TEXT NOT NULL DEFAULT `created` (مقادیر: `created`|`delivered`|`failed`)

### `events`
`event_id` TEXT PK · `request_id` TEXT NOT NULL INDEX · `donor_id` TEXT NULL · `notification_id` TEXT NULL · `kind` TEXT NOT NULL (`donor_response`|`donor_progress`|`gateway_status`|`stock_delivery`) · `response` TEXT NULL (`accepted`|`declined`) · `event` TEXT NULL (`en_route`|`arrived`|`screen_pass`|`screen_fail`|`donated`|`no_show`) · `status` TEXT NULL (`queued`|`sent`|`delivered`|`failed`|`expired`) · `reason` TEXT NULL · `sim_time` REAL NOT NULL · `received_at_sim_min` REAL NOT NULL

### `notifications`
`notification_id` TEXT PK · `request_id` TEXT NOT NULL INDEX · `donor_id` TEXT NOT NULL · `template` TEXT NOT NULL · `created_sim_min` REAL NOT NULL · `sent_sim_min` REAL NULL · `gateway_status` TEXT NULL · `response` TEXT NULL · INDEX روی `(request_id, donor_id)`

### `donors`
`donor_id` TEXT PK · `blood_group` TEXT NOT NULL · `sex` TEXT NOT NULL · `age` INTEGER NOT NULL · `weight_kg` REAL NOT NULL · `lat` REAL NOT NULL · `lon` REAL NOT NULL · `area_id` TEXT NOT NULL INDEX · `quiet_start_hour` INTEGER NOT NULL · `quiet_end_hour` INTEGER NOT NULL · `last_donation_at` TEXT NULL · `last_donation_type` TEXT NULL · `permanently_excluded` INTEGER NOT NULL DEFAULT 0 · `notified_90d` INTEGER NOT NULL DEFAULT 0 · `defer_until` TEXT NULL · `defer_days` INTEGER NULL

### `hospitals`
`hospital_id` TEXT PK · `name` TEXT NOT NULL · `lat` REAL NOT NULL · `lon` REAL NOT NULL · `request_weight` REAL NULL · `credit_level` TEXT NULL

### `centers`
`center_id` TEXT PK · `name` TEXT NOT NULL · `lat` REAL NOT NULL · `lon` REAL NOT NULL · `beds` INTEGER NULL · `open_hour` INTEGER NULL · `close_hour` INTEGER NULL

### `donor_history` (فقطخواندنی، ~۷۰۰هزار سطر — بارگذاری bulk)
`id` INTEGER PK AUTOINCREMENT · `request_id` TEXT NOT NULL · `donor_id` TEXT NOT NULL INDEX · `notified_at` TEXT NULL · `wave` INTEGER NULL · `responded` INTEGER NULL · `accepted` INTEGER NULL · `response_delay_min` REAL NULL · `arrived` INTEGER NULL · `donated` INTEGER NULL

### `tasks` (صف وظایف پسزمینه — ماندگار در DB، قابل re-drive پس از ریاستارت)
`id` INTEGER PK AUTOINCREMENT · `task_type` TEXT NOT NULL (`send_wave`|`stop_outreach`|`reminder`|`sla_check`|`stock_delivery_check`|`alloc_retry`) · `request_id` TEXT NULL · `payload_json` TEXT NOT NULL · `status` TEXT NOT NULL DEFAULT `pending` (`pending`|`done`|`failed`) · `attempts` INTEGER NOT NULL DEFAULT 0 · `created_sim_min` REAL NOT NULL · `next_attempt_sim_min` REAL NOT NULL

---

## ۸. قرارداد داخلی ماژولها (امضای توابع قطعی)

لایهها: `app/api` (routers) → `app/services` (منطق) → `app/domain` (قواعد خالص) → `app/data` (SQLAlchemy + بارگذاری)؛ مرز سرویسهای کیت فقط از `app/ports`.

### ۸.۱ `app/data` (مالک: DEV-02 — مصرفکننده: DEV-01)

```python
# app/data/database.py
def init_engine(settings) -> AsyncEngine          # WAL + busy_timeout + foreign_keys
async def create_all(engine) -> None
def get_session() -> AsyncIterator[AsyncSession]  # FastAPI dependency؛ session بهازای درخواست

# app/data/loader.py
async def load_kit_data(settings, engine) -> KitData   # در startup یکبار فراخوانی میشود
class KitData:
    compat: dict            # compat[product][recipient_group] -> [donor_groups]
    rules: dict             # محتوای rules.yaml
    travel_area_to_hospital: dict   # (area_id, hospital_id) -> float دقیقه
    travel_center_to_hospital: dict # (center_id, hospital_id) -> float دقیقه
    travel_area_to_center: dict     # (area_id, center_id) -> float دقیقه
    epoch: datetime         # 2027-01-15T00:00:00+03:30

# app/data/repositories.py  — تمام دسترسی DB فقط از اینجا (DEV-01 حق کوئری مستقیم ندارد)
class RequestRepository:
    async def create(self, req: Request) -> None
    async def get(self, request_id: str) -> Request | None
    async def get_by_idempotency_key(self, key: str) -> Request | None
    async def list(self, hospital_id: str | None = None, status: str | None = None) -> list[Request]
    async def update(self, req: Request) -> None
class EventRepository:
    async def add_or_ignore(self, ev: Event) -> bool        # False = تکراری (event_id موجود)
    async def exists(self, event_id: str) -> bool
    async def count_for(self, request_id: str, kind: str, field: str, value: str, donor_id: str) -> int
    async def list_for_request(self, request_id: str) -> list[Event]
class DispatchRepository:
    async def add_or_ignore(self, d: Dispatch) -> bool
    async def list_for_request(self, request_id: str) -> list[Dispatch]
    async def due_deliveries(self, sim_min: float) -> list[Dispatch]
class NotificationRepository:
    async def add(self, n: Notification) -> None
    async def get(self, notification_id: str) -> Notification | None
    async def find(self, request_id: str, donor_id: str) -> Notification | None
    async def list_for_request(self, request_id: str) -> list[Notification]
    async def accepted_not_donated(self, request_id: str) -> list[Notification]
class DonorRepository:
    async def get(self, donor_id: str) -> Donor | None
    async def eligible(self, product: str, recipient_group: str, request_id: str, sim_min: float, rules: dict, compat: dict) -> list[Donor]
        # همه فیلترهای بخش ۵.۵ را در SQL اعمال میکند؛ خروجی فقط واجدین
    async def history_features(self, donor_id: str) -> dict      # برای ماژول AI
class TaskRepository:
    async def push(self, task: Task) -> None
    async def pop_due(self, sim_min: float, limit: int) -> list[Task]
    async def finish(self, task_id: int, ok: bool) -> None
class HospitalRepository:
    async def exists(self, hospital_id: str) -> bool
    async def list(self) -> list[Hospital]
class CenterRepository:
    async def list(self) -> list[Center]
```

### ۸.۲ `app/domain` (مالک: DEV-01 — مصرفکننده: DEV-01 و DEV-03)

```python
# app/domain/state_machine.py
STATUSES = ["pending_review","open","mobilizing","partially_fulfilled","fulfilled","cancelled","expired"]
EVENTS = ["approved","wave_started","first_fulfilled","fully_fulfilled","cancelled","expired"]
class InvalidTransitionError(Exception): ...
def transition(current: str, event: str) -> str        # فقط گذرگاههای مجاز؛ وگرنه raise
def is_terminal(status: str) -> bool
def is_amendable(status: str) -> bool

# app/domain/ranking.py — Protocol مشترک (DEV-03 از همین استفاده میکند)
@dataclass
class RankingContext:
    request: Any                 # شیء Request مدل
    hospital: Any                # شیء Hospital مدل
    sim_min: float
    travel_minutes: dict         # donor_id -> دقیقه (ناحیه اهداکننده تا بیمارستان)
@dataclass
class RankedDonor:
    donor_id: str
    score: float                 # بیشتر = اولویت بالاتر
    travel_minutes: float
class DonorRankingStrategy(Protocol):
    name: str
    def rank(self, donors: list, context: RankingContext) -> list[RankedDonor]: ...
```

### ۸.۳ `app/services` (مالک: DEV-01)

```python
# app/services/request_service.py
class RequestService:
    async def create_request(self, payload: dict, idempotency_key: str, sim_min: float) -> CreateResult
        # CreateResult: created:bool, replay:bool, request_id:str, status:str, needed:int
        # یا CreateError(code:str, http_status:int)
    async def get_request_detail(self, request_id: str) -> dict | None      # RequestDetail (بخش ۹)
    async def amend_urgency(self, request_id: str, urgency: str, sim_min: float) -> dict | CreateError
    async def cancel_request(self, request_id: str, sim_min: float) -> dict | CreateError
    async def approve_request(self, request_id: str, approved: bool, sim_min: float) -> dict | CreateError

# app/services/allocation_service.py
class AllocationService:
    async def allocate(self, request_id: str, sim_min: float) -> dict      # {"dispatched_units": int, "shortage": int}

# app/services/invitation_service.py
class InvitationService:
    async def build_wave(self, request_id: str, sim_min: float) -> int     # تعداد پیامهای ارسالشده
    async def stop_outreach(self, request_id: str, template: str) -> int   # template ∈ {not_needed, cancelled}
    async def send_reminders(self, request_id: str, sim_min: float) -> int

# app/services/callback_processor.py
class CallbackProcessor:
    async def process_donor_response(self, payload: dict, sim_min: float) -> bool   # False = تکراری
    async def process_donor_progress(self, payload: dict, sim_min: float) -> bool
    async def process_gateway_status(self, payload: dict, sim_min: float) -> bool

# app/services/sla_service.py
class SlaService:
    async def check_expired(self, sim_min: float) -> list[str]   # request_idهای منقضیشده

# app/ports/clients.py — مرز Hexagonal (مالک: DEV-01)
class ClockClient:
    async def now_sim(self) -> float                # کش TTL=CLOCK_CACHE_TTL_SEC؛ تنها منبع زمان
class GatewayClient:
    async def send_message(self, body: dict) -> SendResult   # retry روی 429/503 با Retry-After؛
        # SendResult: accepted:bool, status:int, duplicate:bool      409 = duplicate و بیخطر
class InventoryClient:
    async def get_inventory(self) -> InventorySnapshot          # {"sim_time", "items"}
    async def dispatch(self, body: dict) -> DispatchResult      # DispatchResult: created, replay, error
class TravelClient:
    async def minutes(self, from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> float | None

# app/tasks/dispatcher.py
class BackgroundDispatcher:
    def start(self) -> None          # asyncio task؛ تیک هر DISPATCHER_TICK_SEC ثانیه واقعی
    async def stop(self) -> None     # در lifespan app
    # در هر تیک: pop_due(tasks) → اجرا؛ sla_check؛ stock_delivery_check؛ alloc_retry برای shortageها
```

### ۸.۴ `app/ai` (مالک: DEV-03 — مصرفکننده: DEV-01 از طریق Protocol)

```python
# app/ai/ranking.py
class AIResponseRankingStrategy:    # DonorRankingStrategy را از app/domain/ranking.py پیاده میکند
    name = "ai_response"
    def __init__(self, model_path: str): ...
    def rank(self, donors, context) -> list[RankedDonor]
        # score = احتمال پذیرش مدل (0..1)؛ اگر مدل بارگذاری نشد → fallback به زمان سفر + WARNING در log
```

نقطه اتصال در `app/main.py`: بر اساس `RANKING_STRATEGY` یکی از دو استراتژی ساخته و به `InvitationService` تزریق میشود. اگر `ai_response` انتخاب شده ولی فایل مدل نباشد → fallback به `travel_time` با log هشدار (سرویس هرگز crash نمیکند).

---

## ۹. قرارداد UI — endpoint های داخلی `/api/*` (مالک: DEV-01 پیادهسازی، DEV-03 مصرف)

این مسیرها **جزو قرارداد رسمی نیستند** و فقط برای رابط کاربری هستند. با مسیرهای رسمی تداخل ندارند.

| Method | Path | Auth | ورودی | خروجی |
|---|---|---|---|---|
| GET | `/api/requests` | hospital یا coordinator | query: `hospital_id?`, `status?` | `{"requests": [RequestDetail...]}` |
| GET | `/api/requests/{request_id}` | hospital یا coordinator | — | `RequestDetail` یا 404 |
| GET | `/api/inventory` | coordinator | — | passthrough: `{"sim_time", "items": [...]}` |
| GET | `/api/hospitals` | hospital | — | `{"hospitals": [{"hospital_id","name"}]}` |
| GET | `/api/centers` | coordinator | — | `{"centers": [{"center_id","name"}]}` |
| GET | `/api/clock` | ندارد | — | `{"sim_time", "epoch", "speed"}` (از ClockClient) |
| GET | `/api/donor/invitations?donor_id=` | ندارد | query donor_id | `{"donor_id", "invitations": [DonorInvitation...]}` |
| POST | `/api/donor/respond` | ندارد | `{"donor_id","request_id","response"}` | `{"ok": true}` یا 400 |
| POST | `/api/donor/progress` | ندارد | `{"donor_id","request_id","event"}` | `{"ok": true}` یا 400 |

دو endpoint آخر (شبیهسازی تعامل اهداکننده در دمو) دقیقاً همان مسیر CallbackProcessor را میروند (با `event_id = "ui-" + uuid4().hex` و `sim_time` از ClockClient) — یعنی دمو رفتار واقعی را نشان میدهد.

### `RequestDetail` (قالب قطعی برای UI)

```json
{
  "request_id": "R-ab12cd34ef56",
  "status": "mobilizing",
  "hospital_id": "H07",
  "blood_group": "O+",
  "product": "red_cells",
  "units": 8,
  "urgency": "critical",
  "note": null,
  "needed": 8,
  "confirmed": 5,
  "en_route": 3,
  "arrived": 2,
  "fulfilled": 3,
  "stock_inflight": 2,
  "shortage": 3,
  "created_sim_min": 123.4,
  "updated_sim_min": 150.0,
  "sla_deadline_sim_min": 213.4,
  "sim_min": 152.0,
  "wave_count": 2,
  "events": [ { "event_id","kind","donor_id","notification_id","response","event","status","reason","sim_time" } ],
  "dispatches": [ { "dispatch_id","request_id","center_id","blood_group","product","units","hospital_id","recipient_blood_group","created_sim_min","delivery_sim_min","outcome" } ]
}
```

### `DonorInvitation`

```json
{ "notification_id": "nt-...", "request_id": "R-...", "template": "request_wave",
  "created_sim_min": 130.0, "gateway_status": "delivered", "response": null, "event": null }
```

قواعد UI (قطعی برای DEV-03):
- Base URL = همان origin (relative fetch)؛ بدون CORS.
- توکنها در `localStorage` با کلیدهای `bloodnet_hospital_token` و `bloodnet_coordinator_token`؛ ورود دستی در هدر هر صفحه.
- Polling: لیست هر ۵ ثانیه، جزئیات هر ۳ ثانیه، موجودی هر ۵ ثانیه.
- خطاها: هر پاسخ خطا `{"error": {"code", "message"}}` → toast فارسی (نگاشت code→پیام در `js/apiClient.js`).
- متنهای UI فارسی و RTL؛ تمام شناسهها و مقادیر انگلیسی.
- اعداد نمایشی فقط از پاسخ API (صداقت اعداد — هرگز عددی را client-side نسازید).

---

## ۱۰. قراردادهای Git (قطعی برای همه)

| موضوع | قانون |
|---|---|
| branch اصلی | `master` — همیشه قابل اجرا؛ commit مستقیم روی آن ممنوع |
| نام branch | `feature/d01-<kebab-slug>` · `fix/d02-<slug>` · `docs/...` · `chore/...` (d01=ثنا، d02=اسرا، d03=شقایق) |
| commit | **انگلیسی**، قالب Conventional: `feat(scope): summary` / `fix(scope): summary` / `test(...)` / `docs(...)` / `refactor(...)` / `chore(...)` / `perf(...)` — سطر اول ≤۷۲ کاراکتر |
| merge | فقط Pull Request به `master`؛ rebase روی master قبل از PR؛ Squash merge؛ بعد از merge شاخه حذف شود |
| review | ثنا reviewer همه PRها؛ PR خود ثنا را اسرا review میکند؛ merge فقط وقتی `harness.contract_tests` سبز است |
| تعارض | نقشه مالکیت فایلها (بخش ۱۱)؛ هیچکس فایل دیگری را ویرایش نمیکند؛ فایلهای مشترک فقط در جلسه یکپارچهسازی با هماهنگی |
| عملیات مخرب | Reset، Force Push، Rebase شاخه مشترک، حذف شاخه یا دستکاری تغییرات commitنشده دیگران — ممنوع مگر با اجازه صریح صاحب کار؛ هر Conflict احتمالی قبل از اقدام گزارش شود |
| ممنوع در repo | `.env`، `*.db`، `__pycache__/`، `.venv/`، `.pytest_cache/`، `run_out/`، `logs/` |
| محرمانه | فقط `.env.example` با توکنهای دموی کیت commit میشود؛ هیچ کلید واقعی وجود ندارد |

دستورهای پرکاربرد:

```bash
git switch -c feature/d01-state-machine master
git add <فایلهای مشخص، نه git add .>
git commit -m "feat(requests): add state machine with approved transitions"
git rebase master && git push -u origin feature/d01-state-machine
# سپس PR در GitHub و squash merge به master
```

---

## ۱۱. نقشه مالکیت فایلها (هیچ تداخلی مجاز نیست)

| مسیر | مالک |
|---|---|
| `app/main.py`، `app/config.py`، `app/api/**` (همه router ها + deps) | DEV-01 ثنا |
| `app/domain/**`، `app/services/**`، `app/ports/**`، `app/tasks/**` | DEV-01 ثنا |
| `app/data/**` (models, database, repositories, loader) | DEV-02 اسرا |
| `static/**` (سه نما + css + js) | DEV-03 شقایق |
| `app/ai/**`، `scripts/train_model.py`، `scripts/evaluate_model.py`، `docs/ai_module.md` | DEV-03 شقایق |
| `requirements.txt`، `.gitignore`، `.env.example`، `scripts/setup.*`، `scripts/run.*`، `scripts/smoke.py`، `README.md`، `DECLARED.md` | DEV-02 اسرا |
| `tests/core/**`، `tests/e2e/**` | DEV-01 ثنا |
| `tests/data/**` | DEV-02 اسرا |
| `tests/ai/**` | DEV-03 شقایق |
| `docs/CONTRACT.md` و سایر اسناد تیم | فقط با تصمیم تیمی تغییر میکند |

قاعده در صورت نیاز متقابل: اگر کسی به متدی در کد دیگری نیاز دارد که در این قرارداد نیست → درخواست کتبی (issue/پیام تیم) → صاحب فایل اضافه میکند. **هیچکس مستقیم فایل دیگری را ویرایش نمیکند.**

---

## ۱۲. راهبرد خطا و Logging (قطعی)

- **خطاهای دامنه** → همان قالب `{"error": {"code","message"}}` با کدهای بخش ۲.۳؛ پیام انگلیسی و کوتاه.
- **خطاهای غیرمنتظره** → log با stack trace + پاسخ 500 با `internal_error` (بدون افشای جزئیات).
- **خطاهای سرویسهای کیت**: retry محدود (`HTTP_MAX_RETRIES` با احترام به `Retry-After`)؛ اگر قطعی ماند → عملیات ناموفق ثبت میشود (dispatch با outcome=failed، وظیفه با attempts+1) و **هیچگاه** پاسخ درخواست کاربر را crash یا block نمیکند؛ درخواست بعدی re-drive میشود.
- **Logging**: فقط `logging` استاندارد پایتون؛ فرمت `%(asctime)s %(levelname)s %(name)s %(message)s`؛ خروجی console + فایل `logs/service.log`؛ سطح از `LOG_LEVEL`. پیامها انگلیسی.
- **ممنوع**: هرگونه `datetime.now()`/`time.time()` برای تصمیمهای شبیهسازی — فقط `ClockClient.now_sim()`.

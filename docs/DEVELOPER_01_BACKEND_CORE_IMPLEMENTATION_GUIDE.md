# DEVELOPER_01_BACKEND_CORE_IMPLEMENTATION_GUIDE.md

**این فایل را کامل بخوان، سپس شروع کن.** تو یک عامل برنامهنویسی هستی و این سند تمام اطلاعات لازم برای پیادهسازی بخش تو را دارد — شامل دستورالعمل اصلی همکاری (محدوده، Git، هماهنگی، قالب خروجی). نیازی به هیچ مکالمه یا سند دیگری نداری (مگر برای جزئیات بیشتر به `docs/CONTRACT.md` در همین مخزن رجوع کنی که منبع نهایی نامهاست).

**مخزن:** `https://github.com/ISanaSaki/SSApro.git` · **شاخه اصلی (protected):** `master`

---

## الف) مشخصات و هویت توسعهدهنده

| مورد | مقدار |
|---|---|
| شناسه عضو | **DEV-01** |
| عضو تیم | ثنا (Backend Lead) |
| نقش اختصاصی | پیادهسازی هسته منطق کسبوکار و لایه API سرویس BloodNet |
| مسئولیت اصلی | ماشین وضعیت، idempotency، تخصیص موجودی، دعوت اهداکننده، پردازش callbackها، کلاینتهای سرویسهای کیت، router های رسمی و UI، سرهمبندی app |
| محدوده دقیق وظایف | تمام فایلهای فهرست بخش «هـ» (فقط همینها) |
| **خارج از محدوده** | `app/data/**` (مال DEV-02)، `static/**` و `app/ai/**` و اسکریپتهای مدل (مال DEV-03)، `README.md`/`DECLARED.md`/`scripts/setup|run|smoke` و `requirements.txt` (مال DEV-02) |

---

## ب) قوانین اصلی همکاری و محدوده (الزامی — بالاترین اولویت)

این بخش از دستورالعمل اصلی مالک پروژه (ثنا) گرفته شده و بر هر بخش دیگر این سند مقدم است:

1. **مسئولیت تو صرفاً بخش DEV-01 است.** تحت هیچ شرایطی وارد پیادهسازی وظایف سایر اعضا نشو.
2. **فایلهای اختصاصی سایر اعضا را ویرایش، حذف، بازنویسی یا جابهجا نکن.** کد دیگران را حتی اگر فنی نیازمند اصلاح باشد، بدون اجازه تغییر نده.
3. **اگر برای تکمیل بخش خودت به کد/API/خروجی بخش دیگری نیاز داشتی:** ابتدا وابستگی را شناسایی کن و فقط راهکار سازگار ارائه بده — هرگز خودسرانه تغییر نده.
4. **اگر بخشی از وظایف تو با عضو دیگری همپوشانی داشت:** قبل از هر تغییری از ثنا تأیید بگیر.
5. **هیچ قابلیتی خارج از محدوده مسئولیت تو توسعه نده.**
6. **هماهنگی API:** قراردادهای موجود (docs/CONTRACT.md) را مبنا قرار بده؛ نوع دادهها، نام فیلدها، ساختار JSON و اعتبارسنجی را دقیقاً هماهنگ نگه دار؛ **از حدس زدن Endpoint یا ساختار داده خودداری کن**؛ در صورت نبود اطلاعات کافی، ابتدا سؤال بپرس. هر تغییر قرارداد API فقط با اعلام قبلی تأثیر آن بر سایر اعضا و تأیید تیم.
7. **Git (ایمنی):** قبل از هر تغییر، وضعیت Git و تغییرات commitنشده را بررسی کن؛ تغییرات سایر اعضا را دستکاری/حذف نکن؛ **از Reset، Rebase روی شاخه مشترک، Force Push یا هر عملیات مخرب بدون اجازه صریح ثنا خودداری کن**؛ تغییرات را محدود، کوچک و قابل بررسی نگه دار؛ در قالب یک مجموعه مستقل و قابل Merge آماده کن؛ هر Conflict احتمالی را **پیش از اقدام** گزارش بده.
8. **قانون نهایی:** کیفیت بالای کد بههیچوجه مجوز عبور از محدوده وظایف نیست. اگر به اطلاعات یا تغییری خارج از محدوده نیاز داشتی، بهجای انجام خودسرانه، شفاف اعلام کن و منتظر تأیید بمان.

---

## ج) معرفی پروژه و اطلاعات موردنیاز

### مسئله
در یک استان ساختگی، بیمارستانها به واحدهای فرآورده خونی نیاز دارند (مثلاً ۲ بامداد، ۸ واحد red_cells گروه O+ با فوریت critical). باید مشخص شود: چقدر موجودی سازگار و غیرمنقضی هست، چقدر تخصیص مییابد، کسری چقدر است، کدام اهداکنندگان واجد شرایط دعوت شوند، و نتیجه هر دعوت چگونه ثبت شود — تا در هر لحظه «تصویر درست» از تأمین/کسری وجود داشته باشد.

### معماری (تأییدشده)
**Modular Monolith + Layered + Hexagonal-lite**: یک فرایند FastAPI روی `:8000` با لایههای `app/api → app/services → app/domain → app/data`؛ سرویسهای کیت فقط از پشت `app/ports`. دیتابیس: SQLite (WAL) از پشت SQLAlchemy async. UI استاتیک توسط همان فرایند سرو میشود.

### فناوریها
Python 3.10+ · FastAPI · Pydantic v2 (pydantic-settings) · SQLAlchemy 2 async + aiosqlite · httpx (async) · pytest + pytest-asyncio · (pandas/scikit-learn فقط در ماژول DEV-03).

### سرویسهای کیت (همیشه در حال اجرا توسط هارنس یا دستی)
- Gateway `http://localhost:9100` — ساعت رسمی و ارسال پیام
- Travel `http://localhost:9200` — زمان سفر
- Inventory `http://localhost:9300` — موجودی زنده و dispatch

### جایگاه بخش تو در کل برنامه
تو هسته محصول را میسازی: تمام منطق، تمام مسیرهای HTTP، و سرهمبندی. DEV-02 لایه داده (مدلها/ریپازیتوریها/بارگذاری) را با **امضای توابع از پیش قفلشده** (بخش و) میسازد و تو مصرف میکنی. DEV-03 رابط کاربری را بر اساس endpoint های `/api/*` که تو میسازی مینویسد و یک استراتژی رتبهبندی هوشمند طبق Protocol تو پیاده میکند.

---

## د) شرح دقیق وظایف اجرایی

### T1 — ماشین وضعیت (`app/domain/state_machine.py`)

- **چرا:** قلب محصول؛ تمام انتقالهای وضعیت درخواست باید صریح، متمرکز و تستپذیر باشند (نیازمندی F3/F7).
- **ورودی/خروجی:** `transition(current: str, event: str) -> str`؛ `is_terminal(status) -> bool`؛ `is_amendable(status) -> bool`.
- **گذرگاههای قطعی:**
  ```
  pending_review --approved--> open
  open --wave_started--> mobilizing
  open|mobilizing --first_fulfilled--> partially_fulfilled
  open|mobilizing|partially_fulfilled --fully_fulfilled--> fulfilled
  open|mobilizing|partially_fulfilled --cancelled--> cancelled
  open|mobilizing|partially_fulfilled --expired--> expired
  ```
- **قواعد:** انتقال نامعتبر → `InvalidTransitionError` (که در service به 409 با کد `not_amendable`/`not_approvable` نگاشت میشود). وضعیتهای پایانی: `fulfilled, cancelled, expired`. قابل اصلاح: `open, mobilizing, partially_fulfilled`.
- **لبهها:** رویداد روی وضعیت پایانی → خطا یا no-op صریح؛ هیچ انتقال ضمنی مجاز نیست.
- **پذیرش:** تست واحد همه گذرگاهها + همه گذرگاههای ممنوع.

### T2 — تنظیمات (`app/config.py`)

- کلاس `Settings` با pydantic-settings؛ کلیدها **دقیقاً** مطابق CONTRACT بخش ۶ (PORT تا DISABLE_OUTREACH). فایل `.env` در ریشه خوانده میشود؛ پیشفرضها = مقادیر همان فهرست. متد `load_settings() -> Settings` با کش در سطح ماژول.

### T3 — کلاینتهای کیت (`app/ports/clients.py`)

- **ClockClient**: `now_sim() -> float` — `GET {GATEWAY_URL}/clock` با کش TTL=`CLOCK_CACHE_TTL_SEC` ثانیه واقعی (async lock برای جلوگیری از thundering herd)؛ در خطا: آخرین مقدار + `logger.warning`. **تنها منبع زمان کل سرویس.**
- **GatewayClient**: `send_message(body) -> SendResult(accepted, status, duplicate)` — POST `/messages` با retry روی 429/503 تا `HTTP_MAX_RETRIES` بار با احترام به هدر `Retry-After` و همان `notification_id`؛ 409 → `duplicate=True` و بیخطر؛ timeout=`HTTP_TIMEOUT_SEC`.
- **InventoryClient**: `get_inventory() -> {"sim_time": float, "items": list}` (retry مشابه) و `dispatch(body) -> DispatchResult(created, replay, error_code|None)`.
- **TravelClient**: `minutes(from_lat, from_lon, to_lat, to_lon) -> float | None` (None در خطا؛ retry محدود).
- **قواعد:** هیچ منطق کسبوکاری اینجا نیست؛ خطاها را به نتایج ساختاریافته تبدیل کن، هرگز exception خام به بالا نده. هرگز `/admin/*` صدا زده نشود.

### T4 — سرویس درخواست (`app/services/request_service.py`)

- `create_request(payload, idempotency_key, sim_min) -> CreateResult | CreateError`:
  1. اعتبارسنجی کامل (hospital ثبتشده، enums، units 1..20، note ≤500، فیلد اضافه → 400).
  2. `hospital_id` نامعتبر → `CreateError(code="unknown_hospital", http_status=400)` — **بدون هیچ موج/موجودی**.
  3. idempotency: هش بدنه = `json.dumps(payload, sort_keys=True)`؛ اگر کلید موجود: هش یکسان → `replay=True` با همان `request_id` (200)؛ متفاوت → `CreateError(code="idempotency_key_reuse", http_status=422)`.
  4. درج رقابتی: ابتدا INSERT با `idempotency_key` UNIQUE؛ اگر `IntegrityError` → دوباره بخوان و طبق بند ۳ عمل کن (تضمین «۲۰ درخواست همزمان → یک درخواست»).
  5. سیاست pending (بخش ۵.۱ CONTRACT): ثبتنشده→رد؛ مشکوک (burst) → `pending_review` بدون هزینه؛ وگرنه → `open` و شروع چرخه (تخصیص + موج ۱) بهصورت async پس از پاسخ (Fire-and-forget از طریق dispatcher/task، نه داخل همین درخواست تا تأخیر HTTP کم بماند).
  6. `request_id = "R-" + uuid4().hex[:12]`؛ `sla_deadline_sim_min = sim_min + sla[urgency]`.
- `get_request_detail(request_id) -> dict | None` — RequestDetail دقیقاً مطابق CONTRACT بخش ۹ (با `shortage`، `sim_min` از ClockClient، events و dispatches از ریپازیتوریها).
- `amend_urgency(request_id, urgency, sim_min)`: فقط وضعیتهای amendable (وگرنه 409 `not_amendable`)؛ `sla_deadline_sim_min = sim_min + sla[new]`؛ موج جدید پس از اصلاح (در صورت shortage).
- `cancel_request(request_id, sim_min)`: وضعیت پایانی → 200 no-op؛ وگرنه `cancelled` + توقف دعوتها با قالب `cancelled`.
- `approve_request(request_id, approved, sim_min)`: فقط `pending_review` (وگرنه 409 `not_approvable`)؛ `approved=False` → `cancelled`؛ `True` → `open` + شروع چرخه.

### T5 — تخصیص موجودی (`app/services/allocation_service.py`)

الگوریتم دقیق در CONTRACT بخش ۵.۴ (فیلتر سازگاری+انقضا → FEFO → dispatch اتمی با `dispatch_id="dsp-"+uuid4().hex` → ثبت در dispatches → `delivery_sim_min = sim_min + 10 + travel(center→hospital)` از `travel_center_to_hospital`). خروجی: `{"dispatched_units": int, "shortage": int}`. هرگز بیشتر از `need` ارسال نشود؛ dispatch ناموفق فقط `outcome=failed` ثبت میشود. `stock_inflight` فقط با تحویل (T8) کم میشود.

### T6 — دعوت اهداکننده (`app/services/invitation_service.py`)

- **پیشفیلتر واجدین (SAFETY GATE — هر خطا = صفر کل امتیاز):** دقیقاً ۷ شرط CONTRACT بخش ۵.۵. از `DonorRepository.eligible(...)` استفاده کن (DEV-02 این فیلتر را در SQL میسازد) و **خروجی را دوباره در پایتون بازبینی کن** (defense-in-depth: tattoo/travel_risk از `defer_until`، سکوت، فاصله اهدا، سازگاری) — ارسال به اهداکننده معلق حتی اگر Gateway رد کند خطای ایمنی است.
- `build_wave(request_id, sim_min) -> int`: واجدین → رتبهبندی با استراتژی تزریقشده → سقف `min(max(shortage*WAVE_SIZE_FACTOR, WAVE_MIN_SIZE), WAVE_MAX_SIZE)` → ارسال `request_wave` (notification_id=`"nt-"+uuid4().hex`, callback_url=SELF_URL) → ثبت در notifications + `wave_count+=1` + گذرگاه `wave_started` → task موج بعدی (`WAVE_INTERVAL_MIN` بعد، اگر wave_count < WAVE_MAX_COUNT و هنوز shortage).
- `stop_outreach(request_id, template) -> int`: برای accepted های بدون donated → ارسال `not_needed` (در fulfilled) یا `cancelled` (در cancel/expired).
- `send_reminders(request_id, sim_min)`: به accepted های بدون arrived بعد از `REMINDER_INTERVAL_MIN` → قالب `reminder`.
- استراتژی پیشفرض `TravelTimeRankingStrategy` (name=`travel_time`): صعودی زمان سفر (از `RankingContext.travel_minutes`)، تساویشکن صعودی `notified_90d`. استراتژی از طریق سازنده تزریق میشود (Protocol در `app/domain/ranking.py`).
- خروجی همیشه int تعداد ارسال موفق؛ خطای Gateway نباید wave را کرش کند.

### T7 — پردازش callback (`app/services/callback_processor.py`)

- سه متد: `process_donor_response / process_donor_progress / process_gateway_status`؛ هرکدام `bool` (False = event تکراری).
- **dedup:** `EventRepository.add_or_ignore(event_id)` — تکراری → False و هیچ تغییری.
- **request ناشناخته** → ثبت رویداد و True (پاسخ 200) بدون تغییر شمارنده (قرارداد).
- `donor-response`:
  - `accepted`: اگر برای این `(request_id, donor_id)` قبلاً accepted نشده → `confirmed += 1` + ارسال قالب `confirmed`. نگهبان: `EventRepository.count_for(...)` یا چک notifications.response.
  - `declined`: ثبت reason؛ بدون تغییر شمارنده.
- `donor-progress`:
  - `en_route`/`arrived`: هرکدام حداکثر یکبار بهازای `(request_id, donor_id)` → شمارنده مربوطه += 1.
  - `donated`: حداکثر یکبار → `fulfilled += 1`؛ اگر `fulfilled >= needed` → گذرگاه `fully_fulfilled` + `stop_outreach(request, "not_needed")`؛ اگر قبلاً 0 بود → گذرگاه `first_fulfilled`.
  - `screen_pass/screen_fail/no_show`: فقط ثبت؛ بدون شمارنده.
- `gateway-status`: فقط بهروزرسانی `notifications.gateway_status`؛ بدون شمارنده درخواست.
- ترتیب نامرتب و تکرار: همهچیز از dedup + نگهبانها میگذرد؛ هیچ فرضی روی ترتیب نکن.

### T8 — سرویس SLA و تحویل موجودی (`app/services/sla_service.py` + داخل dispatcher)

- `check_expired(sim_min) -> list[str]`: درخواستهای باز با `sla_deadline_sim_min <= sim_min` → گذرگاه `expired` + `stop_outreach(cancelled)`.
- تحویل موجودی: dispatchهای `outcome=created` با `delivery_sim_min <= sim_min` → `outcome=delivered`، `stock_inflight -= units`، `fulfilled += units`، رویداد داخلی `stock_delivery` با `event_id="sd-"+dispatch_id`؛ سپس همان بررسی fully_fulfilled + گذرگاهها.

### T9 — حلقه پسزمینه (`app/tasks/dispatcher.py`)

- یک asyncio task در lifespan؛ تیک هر `DISPATCHER_TICK_SEC` ثانیه واقعی:
  1. `TaskRepository.pop_due(sim_min, limit)` → اجرا بر اساس `task_type` (send_wave/stop_outreach/reminder/alloc_retry/sla_check/stock_delivery_check)؛ موفق → `finish(ok=True)`، خطا → attempts+1 و `next_attempt_sim_min` بعدی (حداکثر ۳ بار، سپس failed).
  2. همیشه: sla_check + stock_delivery_check + alloc_retry برای درخواستهای باز دارای shortage (هر `ALLOC_RETRY_INTERVAL_MIN`).
- در startup: وظایف pending در DB خودشان re-drive میشوند (چیزی در حافظه گم نمیشود).
- **هشدار:** ساعت فقط از ClockClient؛ تیک حلقه بر حسب ثانیه واقعی است ولی همه تصمیمها با `sim_min`.

### T10 — لایه API (`app/api/`)

- `deps.py`: `require_hospital_token` و `require_coordinator_token` (مقایسه با تنظیمات با `secrets.compare_digest`؛ غایب/غلط → 401 `unauthorized`).
- `routers/requests.py`: مسیرهای رسمی بخش ۲.۱ CONTRACT با کدهای خطای قطعی (جدول ۲.۳). پاسخ 201 ساخت: `{"request_id", "status", "needed"}`؛ replay: 200 همان. خطاهای Pydantic → 400 با `validation_error` (نه 422 خودکار — قرارداد میگوید 400). هدر `Idempotency-Key` غایب → 400 `missing_idempotency_key`. `X-Sim-Time` خوانده ولی نادیده گرفته میشود (فقط ClockClient ملاک است).
- `routers/callbacks.py`: سه مسیر؛ بدنه نامعتبر → 400؛ موفق → 200 `{"ok": true}`.
- `routers/health.py`: `GET /health` بدون auth → `{"ok": true}`.
- `routers/ui.py`: ۹ مسیر `/api/*` دقیقاً مطابق CONTRACT بخش ۹. `POST /api/donor/respond|progress` → ساخت event با `event_id="ui-"+uuid4().hex` و `sim_time` از ClockClient و فراخوانی همان CallbackProcessor (مسیر واقعی دامنه). `GET /api/inventory` → passthrough InventoryClient. `GET /api/clock` → از ClockClient با epoch و speed.
- `main.py`: ساخت FastAPI؛ lifespan: `init_engine` + `create_all` + `load_kit_data` (از DEV-02) + ساخت BackgroundDispatcher و استارت/استاپ؛ انتخاب استراتژی بر اساس `RANKING_STRATEGY` (import کردن `AIResponseRankingStrategy` از `app.ai.ranking` داخل تابع — import داینامیک تا نبود ماژول DEV-03 سرویس را نشکند؛ خطا → fallback `travel_time` + warning)؛ نصب routers؛ `StaticFiles(directory="static", html=True)` روی `/`؛ `mount` بعد از router ها.

---

## هـ) فایلهایی که باید ایجاد یا ویرایش شوند (فقط همینها)

| مسیر | کلاسها/توابع اصلی |
|---|---|
| `app/__init__.py` | — |
| `app/config.py` | `Settings`، `load_settings()` |
| `app/main.py` | `create_app()`، lifespan |
| `app/api/__init__.py`، `app/api/deps.py` | `require_hospital_token`، `require_coordinator_token` |
| `app/api/routers/__init__.py`، `health.py`، `requests.py`، `callbacks.py`، `ui.py` | handler های هر مسیر |
| `app/domain/__init__.py`، `state_machine.py`، `ranking.py` | مطابق بخش ۸.۲ CONTRACT |
| `app/services/__init__.py`، `request_service.py`، `allocation_service.py`، `invitation_service.py`، `callback_processor.py`، `sla_service.py` | مطابق بخش ۸.۳ CONTRACT |
| `app/ports/__init__.py`، `clients.py` | ۴ کلاینت |
| `app/tasks/__init__.py`، `dispatcher.py` | `BackgroundDispatcher` |
| `tests/core/` | فهرست بخش «ط» |
| `tests/e2e/` | `test_full_flow.py` |

همه نامها و امضاها **دقیقاً** مطابق CONTRACT بخشهای ۶، ۷، ۸، ۹ — بدون استثنا. هر فایل دیگری که لازم دیدی تغییر کنی، **خارج از محدوده است** → طبق بخش «ب» گزارش بده و منتظر تأیید بمان.

---

## و) قراردادهای ارتباطی با سایر بخشها

### چیزهایی که تو پیادهسازی میکنی و دیگران مصرف میکنند
1. **رابطهای `app/data` (بخش ۸.۱ CONTRACT)** — اینها را DEV-02 با همین امضاها میسازد؛ تو فقط مصرف میکنی و **حق ویرایش فایلها را نداری**.
2. **`DonorRankingStrategy` Protocol** (`app/domain/ranking.py`) — DEV-03 آن را در `app/ai/ranking.py` پیاده میکند؛ تو فقط از طریق Protocol مصرف میکنی.
3. **endpoint های `/api/*`** (CONTRACT بخش ۹) — DEV-03 دقیقاً اینها را صدا میزند؛ DTOهای `RequestDetail` و `DonorInvitation` را عیناً تولید کن.

### چیزهایی که از دیگران دریافت میکنی
- از DEV-02: `init_engine`، `create_all`، `load_kit_data`، `get_session`، ۸ ریپازیتوری، مدلهای SQLAlchemy (`Request`, `Dispatch`, `Event`, `Notification`, `Donor`, `Hospital`, `Center`, `Task`).
- از DEV-03: `AIResponseRankingStrategy` (اختیاری — سرویس تو بدون آن هم باید کامل کار کند).

### قرارداد رسمی با هارنس (خلاصه — جزئیات در CONTRACT بخش ۲)
- `POST /requests` با `Idempotency-Key` اجباری → 201/200/422/400/401.
- `GET /requests/{id}` → حداقل ۶ فیلد اجباری RequestState.
- callbackها → 200 idempotent؛ بدنه خراب → 400.
- قالب خطا `{"error": {"code", "message"}}`؛ کد `idempotency_key_reuse` دقیقاً همین.

---

## ز) دستورالعمل دقیق پیادهسازی (گامبهگام)

### گام ۰ — بررسی اولیه و گزارش (قبل از نوشتن حتی یک خط کد — الزامی)

1. تمام مستندات را مطالعه کن (این فایل + `docs/CONTRACT.md` + `participant_kit/openapi.yaml` + `starter/starter_app.py` بهعنوان مرجع رفتار).
2. ساختار Repository و وضعیت `git status` را بررسی کن؛ Branchهای موجود (`master` protected) و تغییرات commitنشده دیگران را بشناس.
3. معماری فعلی، نامگذاریها و استانداردهای موجود را شناسایی کن.
4. وابستگی بخش خودت به سایر بخشها (d02 لایه داده، d03 UI/AI) را فهرست کن.
5. **گزارش کوتاه ارائه بده** شامل: معماری پروژه، محدوده دقیق وظایف تو، فایلهای مجاز برای تغییر، وابستگیها و ریسکهای احتمالی.
6. **تا زمانی که محدوده وظایف و وابستگیها تأیید نشده، وارد پیادهسازی نشو.**

### گام ۱ — شاخه و ترتیب ساخت

- `git switch -c feature/d01-core master` — هرگز مستقیم روی `master` کار نکن.
- ترتیب: (a) `config.py` + `state_machine.py` + `ranking.py` + `ports/clients.py` (مستقل از data، فوراً قابل تست) → (b) `services/*` با تزریق session factory و clock (امضاهای `app/data` قفل شدهاند؛ DEV-02 موازی میسازد) → (c) `deps.py` + router های رسمی + `ui.py` → (d) `dispatcher.py` + اتصال در `main.py`.

### گام ۲ — قواعد کدنویسی

- snake_case؛ بدون کامنت اضافی؛ بدون TODO؛ بدون شبهکد؛ async همهجا (بدون blocking call در مسیر درخواست).
- هیچ `datetime.now()`/`time.time()` برای تصمیم شبیهسازی؛ فقط `ClockClient.now_sim()`.
- همه سقفها/آستانهها از `Settings` — هیچ عددی hard-code نشود.
- خطاها فقط به قالب `{"error":{"code","message"}}` با کدهای CONTRACT؛ استثناهای غیرمنتظره → log کامل + 500 `internal_error` (بدون افشای جزئیات).
- امنیت: مقایسه توکن با `secrets.compare_digest`؛ ورودیها فقط از Pydantic؛ بدون eval/exec؛ پارامترهای bind شده.
- Clean Code و SOLID در حد منطقی پروژه؛ از Overengineering پرهیز کن (هیچ لایه/کلاس اضافه بدون نیازمندی مشخص).

### گام ۳ — تست و کیفیت

- تستهای بخش «ط» را همگام بنویس و اجرا کن: `python -m pytest tests/core -q`.
- `python -m compileall app`؛ در صورت وجود ruff اجرا کن.
- سناریوهای موفق و ناموفق + ورودیهای نامعتبر و شرایط مرزی را پوشش بده.

### گام ۴ — PR (مجموعه مستقل و قابل Merge)

- قبل از PR: `git status` را چک کن (فقط فایلهای خودت staged باشند — هرگز `git add .` بدون بازبینی).
- تغییرات را در یک مجموعه مستقل و قابل بازبینی آماده کن؛ commit های کوچک انگلیسی `feat(scope): ...`.
- **ممنوع:** Reset، Rebase شاخه مشترک، Force Push — بدون اجازه صریح. Conflict احتمالی را پیش از اقدام گزارش بده.
- بعد از Merge شدن لایه data (DEV-02)، PR خودت را روی آخرین `master` rebase کن (فقط شاخه خودت) و اجرای کامل تستها را در توضیح PR بیاور.

---

## ح) استانداردهای کد (خلاصه الزامات مالک پروژه)

- Clean Code و خوانایی بالا؛ معماری اصولی و مقیاسپذیر؛ قابلیت نگهداری.
- عملکرد بهینه (کوئریهای کوتاه، بدون کار اضافه در حلقه درخواست).
- مدیریت صحیح خطاها و استثناها؛ اصول امنیتی؛ جلوگیری از تکرار کد.
- SOLID در موارد مناسب؛ الگوهای طراحی فقط وقتی مشکل واقعی را حل میکنند (State Machine، DI، Repository، Strategy، Factory ساده در NotificationBuilder).
- مستندسازی فقط قسمتهای ضروری (docstring کوتاه برای قراردادهای عمومی؛ بدون کامنت اضافه).
- سازگاری کامل با ساختار فعلی پروژه — از تغییرات غیرضروری در ساختار خودداری کن.

---

## ط) الزامات تست

پوشه `tests/core/` (pytest + pytest-asyncio؛ mock کردن ports با monkeypatch/httpx MockTransport؛ DB تستی = sqlite در حافظه):

| فایل | پوشش | نتیجه مورد انتظار |
|---|---|---|
| `test_state_machine.py` | همه گذرگاههای مجاز و ممنوع | ۱۰۰٪ گذرگاهها پاس |
| `test_idempotency.py` | replay 200؛ بدنه متفاوت 422؛ **۲۰ درخواست همزمان با یک کلید → فقط ۱ ساخت** (asyncio.gather) | ۱×201 و ۱۹×200 با همان id |
| `test_requests_api.py` | قرارداد کامل: 201، 400 (کلید غایب/گروه غلط/units 0 و 21)، 401، 404، amend 409/200، cancel دوبار 200/200، approve با توکن اشتباه 401 | همه پاس |
| `test_allocation.py` | FEFO (نزدیکترین انقضا اول)، فیلتر منقضی، فیلتر سازگاری (ماتریس)، dispatch ناموفق → موجودی محلی تغییر نکند، dispatch تکراری idempotent | همه پاس |
| `test_callbacks.py` | dedup با event_id؛ donated قبل از arrived؛ request ناشناخته → 200 بدون شمارش؛ هر شمارنده حداکثر یکبار بهازای donor؛ فقط donated → fulfilled | همه پاس |
| `test_invitation.py` | **هر ۷ فیلتر واجدین** (تعلیق tattoo/travel_risk با آخرین رویداد، سن، وزن، فاصله اهدا، سکوت، سازگاری، تکراری)؛ سقف موج؛ توقف با not_needed پس از fulfilled | **صفر پیام به معلقین** |
| `test_sla.py` | انقضا در مرز sla_deadline؛ amend → deadline جدید؛ expired → توقف دعوت | همه پاس |

`tests/e2e/test_full_flow.py`: جریان کامل ساخت → approve → dispatch → موج → accepted → donated → fulfilled با mock کیت. دستور اجرا: `python -m pytest tests/ -q` از ریشه.

علاوه بر تستهای واحد، قرارداد سیاهجعبه را هم بزن: `python -m harness.contract_tests --team http://127.0.0.1:8000` (نیازمند اجرای سرویس). **تستها نباید مستلزم تغییر غیرمجاز در کد سایر اعضا باشند.**

---

## ی) معیارهای اتمام کار (چکلیست)

- [ ] گزارش اولیه (گام ۰) ارائه و تأیید شده است.
- [ ] همه فایلهای بخش «هـ» ساخته شدهاند؛ هیچ فایلی خارج از مالکیت تو تغییر نکرده است.
- [ ] همه نامها/امضاها با CONTRACT بخشهای ۶، ۷، ۸، ۹ مطابقاند (بدون هیچ نام ابداعی).
- [ ] `pytest tests/core tests/e2e -q` سبز است (خروجی واقعی، نه ادعا).
- [ ] `harness.contract_tests` روی سرویس اجرا شده و همه PASS است.
- [ ] سناریوی P-normal با `harness.runner` کامل اجرا شده و `safety=1` است.
- [ ] صفر اعلان به اهداکنندگان معلق در سناریوها (چک از log/شمارنده).
- [ ] grep کد برای `datetime.now`/`time.time` در منطق شبیهسازی → هیچ موردی نیست.
- [ ] سرویس بدون ماژول DEV-03 و بدون سرویسهای کیت (حالت fallback) استارت میخورد و `/health` پاسخ میدهد.
- [ ] تغییرات در یک مجموعه مستقل و قابل Merge روی شاخه `feature/d01-core` آماده است؛ هیچ عملیات مخرب Git انجام نشده.
- [ ] گزارش نهایی مطابق بخش «ک» تحویل داده شده است.

---

## ک) قالب گزارش نهایی (بعد از تکمیل بخش تو)

1. توضیح معماری و منطق پیادهسازی.
2. فهرست دقیق فایلهای ایجادشده.
3. فهرست دقیق فایلهای ویرایششده.
4. کد کامل و نهایی بخش تو.
5. توضیح ارتباط آن با سایر بخشهای پروژه.
6. توضیح APIهای استفادهشده و قراردادهای مربوطه.
7. گزارش تستهای اجراشده و نتایج آنها (با خروجی واقعی — هرگز ادعای اجرای تستی که اجرا نشده).
8. وابستگیها و تنظیمات موردنیاز.
9. دستورالعمل اجرای بخش تو.
10. مواردی که برای Merge با کد سایر اعضا باید رعایت شوند.

---

## ل) اولویتهای تصمیمگیری (به ترتیب — در هر ابهام)

1. عدم دخالت در وظایف سایر اعضا.
2. رعایت دقیق مستندات رسمی و مستندات پروژه (CONTRACT.md).
3. حفظ سازگاری با معماری و کد فعلی Repository.
4. هماهنگی کامل APIهای مرتبط.
5. جلوگیری از تداخل و Conflict در Git.
6. کیفیت، امنیت، پایداری و مقیاسپذیری کد.

**قانون نهایی:** کیفیت بالای کد بههیچوجه مجوز عبور از محدوده وظایف نیست. اگر به اطلاعات یا تغییری خارج از محدوده نیاز داشتی، شفاف اعلام کن و منتظر تأیید بمان.

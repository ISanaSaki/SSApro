# DEVELOPER_02_BACKEND_DATA_IMPLEMENTATION_GUIDE.md

**این فایل را کامل بخوان، سپس شروع کن.** تو یک عامل برنامهنویسی هستی و این سند تمام اطلاعات لازم برای پیادهسازی بخش تو را دارد. نیازی به هیچ مکالمه یا سند دیگری نداری (مگر برای جزئیات بیشتر به `docs/CONTRACT.md` در همین مخزن رجوع کنی که منبع نهایی نامهاست).

---

## الف) مشخصات و هویت توسعهدهنده

| مورد | مقدار |
|---|---|
| شناسه عضو | **DEV-02** |
| عضو تیم | اسرا (Backend پشتیبان — Data & Delivery) |
| نقش اختصاصی | لایه داده (مدلها، اتصال DB، بارگذاری کیت، ریپازیتوریها) + زیرساخت اجرا و تحویل (اسکریپتها، وابستگیها، مستندات) |
| مسئولیت اصلی | `app/data/**`، `requirements.txt`، `.gitignore`، `.env.example`، `scripts/setup|run|smoke`، `README.md`، `DECLARED.md`، `tests/data/**` |
| محدوده دقیق وظایف | تمام فایلهای فهرست بخش «د» |
| **خارج از محدوده** | `app/api/**`، `app/domain/**`، `app/services/**`، `app/ports/**`، `app/tasks/**`، `app/main.py`، `app/config.py` (مال DEV-01)؛ `static/**`، `app/ai/**`، `scripts/train_model.py`، `scripts/evaluate_model.py` (مال DEV-03). **هرگز این فایلها را ویرایش نکن.** اگر DEV-01 به متدی نیاز دارد که در قرارداد بخش ۸.۱ نیست، او درخواست میدهد و **تو** اضافه میکنی. |

---

## ب) معرفی پروژه و اطلاعات موردنیاز

### مسئله
در یک استان ساختگی، بیمارستانها درخواست فرآورده خونی میدهند؛ سرویس BloodNet موجودی مراکز را با سازگاری و FEFO تخصیص میدهد، برای کسری اهداکنندگان واجد شرایط را از طریق Gateway شبیهسازیشده دعوت میکند و پاسخها را idempotent پردازش میکند تا در هر لحظه تصویر درستی از تأمین/کسری وجود داشته باشد.

### معماری (تأییدشده)
**Modular Monolith + Layered**: یک فرایند FastAPI روی `:8000`؛ لایهها `app/api → app/services → app/domain → app/data`. سرویسهای کیت (Gateway :9100، Travel :9200، Inventory :9300) فقط از `app/ports` (مال DEV-01) صدا زده میشوند. دیتابیس: **SQLite با WAL از پشت SQLAlchemy 2 async** — صفر وابستگی استقرار (داخل خود پایتون)؛ الگوی «شروع تازه در هر اجرا» → `metadata.create_all` کافی است و Alembic عمداً استفاده نمیشود.

### فناوریهای بخش تو
Python 3.10+ · SQLAlchemy 2.0 (async) + aiosqlite · PyYAML · csv ماژول استاندارد · pytest + pytest-asyncio.

### جایگاه بخش تو در کل برنامه
لایه تو **پایه** است: DEV-01 تمام منطق (services) را روی ریپازیتوریها و مدلهای تو میسازد؛ بدون تو هیچچیز بالا نمیآید. کیفیت و سرعت لایه تو (بهویژه بارگذاری ۷۰۰هزار سطر history و فیلتر واجدین) مستقیماً بر امتیاز کل اثر دارد. تو همچنین «تحویل» را تضمین میکنی: اجرای یکدستوری از محیط تمیز که داوران بازاجرا میکنند.

---

## ج) شرح دقیق وظایف اجرایی

### T1 — موتور دیتابیس (`app/data/database.py`)

- `init_engine(settings) -> AsyncEngine`: ساخت engine از `settings.DATABASE_URL` با `sqlite+aiosqlite`؛ اجرای PRAGMA ها هنگام اتصال: `journal_mode=WAL`، `busy_timeout=10000`، `foreign_keys=ON`، `synchronous=NORMAL` (رویداد listener روی connect).
- `create_all(engine)`: `Base.metadata.create_all` (run_sync).
- `get_session() -> AsyncIterator[AsyncSession]`: وابستگی FastAPI — `async_sessionmaker` با `expire_on_commit=False`؛ session بهازای درخواست؛ commit خودکار در پایان موفق + rollback در خطا.
- **چرا:** WAL اجازه خواندن همزمان با نوشتن را میدهد (هارنس با ۱۲۸ worker همزمان callback میفرستد)؛ busy_timeout جلوی `database is locked` را میگیرد؛ یک session بهازای درخواست = واحد کار اتمی (F4/F10).

### T2 — مدلهای SQLAlchemy (`app/data/models.py`)

- کلاس `Base(DeclarativeBase)` و ۹ کلاس مدل **دقیقاً** مطابق CONTRACT بخش ۷: `Request`، `Dispatch`، `Event`، `Notification`، `Donor`، `Hospital`، `Center`، `DonorHistory`، `Task`.
- نام کلاسها و نام جدولها (`__tablename__`): `requests`، `dispatches`، `events`، `notifications`، `donors`، `hospitals`، `centers`، `donor_history`، `tasks`.
- قیود قطعی: `requests.idempotency_key` UNIQUE؛ `events.event_id` PK (dedup ذاتی)؛ `dispatches.dispatch_id` PK؛ ایندکسها دقیقاً طبق CONTRACT (بهویژه `donor_history.donor_id`، `donors.area_id`، `requests.hospital_id`، `notifications(request_id, donor_id)`).
- نوع ستونها: TEXT برای id ها و enums (رشتهای)، INTEGER برای شمارندهها با default=0، REAL برای sim_min.
- بدون رابطه lazy سنگین؛ کوئریهای صریح در ریپازیتوریها.

### T3 — بارگذاری داده کیت (`app/data/loader.py`)

- `load_kit_data(settings, engine) -> KitData` (در startup یکبار):
  1. خواندن `compat.yaml` و `rules.yaml` از `KIT_PATH` → `KitData.compat` و `KitData.rules`.
  2. بارگذاری ۴ ماتریس travel به dict: `travel_area_to_hospital[(area_id, hospital_id)] -> float`، `travel_center_to_hospital[(center_id, hospital_id)] -> float`، `travel_area_to_center[(area_id, center_id)] -> float` (ماتریس `travel_matrix_areas.csv` فقط در صورت نیاز ماژول AI؛ پیشفرض لازم نیست).
  3. بارگذاری CSV ها به جداول با **bulk insert** (raw executemany یا `insert().values([...])` — نه ORM تکتک):
     - `donors.csv` (۲۰هزار سطر) → `donors`
     - `hospitals.csv`، `centers.csv` → جداولشان
     - `history/responses.csv` (~۷۰۲هزار سطر) → `donor_history`
  4. `donor_events.csv` → محاسبه `defer_until` و `defer_days` بهازای هر donor با قاعده **آخرین رویداد جایگزین قبلی میشود** (مرتبسازی بر اساس `event_at`؛ بهازای هر donor فقط رکورد نهایی در ستونهای `defer_until/defer_days` جدول donors ثبت میشود؛ رویدادهای خام جداگانه ذخیره نمیشوند).
  5. `epoch = datetime(2027, 1, 15, tzinfo=...)` ثابت.
  6. همه فایلها از `KIT_PATH` خوانده میشوند؛ اگر فایلی نبود → خطای صریح در startup (fail fast با پیام انگلیسی).
- **هدف عملکردی:** کل بارگذاری باید در چند ثانیه انجام شود (زیر ~۱۵ ثانیه روی لپتاپ معمولی). تاریخچه ۷۰۰هزار سطری نباید سرعت استارت دمو را بشکند.
- دادهها immutable هستند؛ فقط یکبار بارگذاری.

### T4 — ریپازیتوریها (`app/data/repositories.py`)

هشت کلاس با **امضای دقیق** CONTRACT بخش ۸.۱: `RequestRepository`، `EventRepository`، `DispatchRepository`، `NotificationRepository`، `DonorRepository`، `TaskRepository`، `HospitalRepository`، `CenterRepository`. همه از session تزریقشده استفاده میکنند؛ هیچ منطق کسبوکار در اینها نیست (فقط کوئری).

نکات قطعی پیادهسازی:
- `EventRepository.add_or_ignore(ev) -> bool`: تلاش INSERT؛ `IntegrityError` روی PK → False (تکراری)؛ در غیر این صورت True. این مکانیزم dedup سطح DB است (F7/F10).
- `RequestRepository.create`: INSERT؛ `IntegrityError` روی idempotency_key → None (رقابت همزمان — سرویس دوباره میخواند).
- `DonorRepository.eligible(product, recipient_group, request_id, sim_min, rules, compat) -> list[Donor]`: **همه ۷ فیلتر بخش ۵.۵ CONTRACT در یک کوئری SQL** (permanently_excluded، سن، وزن، `defer_until` بر حسب دقیقه شبیهسازی، فاصله اهدا با `last_donation_at` و `last_donation_type` و قواعد interval/cross_block، سکوت با محاسبه ساعت محلی از `sim_min`، سازگاری از `compat[product][recipient_group]` بهصورت لیست IN، و NOT EXISTS در notifications برای این request). خروجی: فقط واجدین.
- `DonorRepository.history_features(donor_id) -> dict`: تجمیع از `donor_history` (تعداد notified/responded/accepted/donated، نرخها، میانگین `response_delay_min`) — برای DEV-03.
- `TaskRepository.pop_due(sim_min, limit)`: `status='pending' AND next_attempt_sim_min <= sim_min` مرتب بر اساس id؛ بدون قفل اضافه (تک مصرفکننده).

### T5 — وابستگیها و محیط اجرا

- `requirements.txt` (پینشده با `==`):
  ```
  fastapi, uvicorn[standard], pydantic>=2, pydantic-settings,
  sqlalchemy>=2, aiosqlite, httpx, PyYAML,
  pytest, pytest-asyncio,
  pandas>=2.0, numpy>=1.26, scikit-learn>=1.3, joblib
  ```
  (pandas/numpy/scikit-learn/joblib برای ماژول هوشمند DEV-03 لازم است — در همین فایل باشند تا اجرای یکدستوری کامل باشد.)
- `.gitignore`: `.env`، `*.db`، `*.db-wal`، `*.db-shm`، `__pycache__/`، `.venv/`، `.pytest_cache/`، `run_out/`، `logs/`، `*.pyc`.
- `.env.example`: دقیقاً کلیدهای CONTRACT بخش ۶ با مقادیر همان فهرست (شامل توکنهای دموی کیت — راز واقعی وجود ندارد).

### T6 — اسکریپتهای اجرا

- `scripts/setup.ps1` (و `setup.sh`): ساخت `.venv` با `python -m venv`، فعالسازی، `pip install -r requirements.txt`. باید از محیط تمیز (کلون تازه) جواب بدهد.
- `scripts/run.ps1` (و `run.sh`): خواندن `.env` در صورت وجود، سپس `python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT` از ریشه مخزن. **یک فرمان، یک فرایند** (F15).
- `scripts/smoke.py`: اسکریپت پایتون که: (۱) `harness.contract_tests` را subprocess اجرا میکند، (۲) سناریوی `P-normal` را با `harness.runner` اجرا میکند، (۳) خلاصه `run_out/result.json` (score، safety، notif_per_unit، overfill) را چاپ میکند. خروجی = شواهد تست برای DECLARED.
- فرمان دموی کامل در README: `scripts/setup.ps1 && scripts/run.ps1` + باز کردن `http://localhost:8000`.

### T7 — مستندات تحویل

- `README.md` (فارسی، مختصر): پروژه چیست، پیشنیاز (فقط Python 3.10+)، نصب/اجرای یکدستوری، سه نمای UI و توکنها (دموی از `.env.example`)، اجرای تستها و smoke، مسیر دمو.
- `DECLARED.md` (فارسی): اعلام صادقانه قابلیتها برای داوران — هسته کامل قرارداد (idempotency، ماشین وضعیت، FEFO+سازگاری، دعوت واجدین با فیلتر تعلیق، callback های idempotent، ساعت شبیهسازی، تلاش مجدد، مهار تقلب)، سه رابط کاربری، شواهد تست؛ بخش ماژول هوشمند را DEV-03 مینویسد و به تو میدهد تا اینجا ادغام کنی (فقط اگر واقعاً کار میکند — قابلیت اعلامشده ولی ناقص = جریمه). Docker: فقط اگر واقعاً ساخته و تست شد.
- هر دو فایل قبل از تحویل نهایی با خروجیهای واقعی (نام فایلهای شواهد) بهروز شوند.

---

## د) فایلهایی که باید ایجاد یا ویرایش شوند

| مسیر | مسئولیت |
|---|---|
| `app/data/__init__.py` | خالی/اکسپورت |
| `app/data/database.py` | `init_engine`، `create_all`، `get_session` |
| `app/data/models.py` | `Base` + ۹ مدل (CONTRACT بخش ۷) |
| `app/data/loader.py` | `load_kit_data` + `KitData` |
| `app/data/repositories.py` | ۸ ریپازیتوری (CONTRACT بخش ۸.۱) |
| `requirements.txt` | وابستگیهای پینشده |
| `.gitignore` | مطابق T5 |
| `.env.example` | کلیدهای CONTRACT بخش ۶ |
| `scripts/setup.ps1`، `scripts/setup.sh` | نصب محیط |
| `scripts/run.ps1`، `scripts/run.sh` | اجرای یکدستوری |
| `scripts/smoke.py` | تست قرارداد + سناریوی تمرینی |
| `README.md` | راهنمای نصب/اجرا/دمو |
| `DECLARED.md` | اعلام رسمی قابلیتها |
| `tests/data/` | تستهای لایه داده (بخش ز) |

---

## هـ) قراردادهای ارتباطی با سایر بخشها

### چیزهایی که تو پیادهسازی میکنی و دیگران مصرف میکنند
1. **امضای توابع `app/data`** (CONTRACT بخش ۸.۱) — DEV-01 در services و main دقیقاً با همین نامها/پارامترها صدا میزند. **هر تغییری = شکستن بکاند.** تغییر فقط با تصمیم تیمی و بهروزرسانی CONTRACT.
2. **`KitData`** با فیلدهای: `compat`، `rules`، `travel_area_to_hospital`، `travel_center_to_hospital`، `travel_area_to_center`، `epoch`.
3. **مدلهای SQLAlchemy** با نام کلاسهای `Request/Dispatch/Event/Notification/Donor/Hospital/Center/DonorHistory/Task` — DEV-01 از آنها import میکند.
4. **`scripts/smoke.py`** — همه تیم و داوران استفاده میکنند.

### چیزهایی که از دیگران دریافت میکنی
- از DEV-01: هیچچیز (تو مستقلترین عضو هستی). اما `app/main.py` (مال او) توابع تو را در startup صدا میزند: `init_engine(settings)` → `create_all(engine)` → `load_kit_data(settings, engine)` → `get_session()` بهعنوان dependency. مطمئن شو امضاها همین است.
- از DEV-03 (اواخر کار): بخش «ماژول هوشمند» برای `DECLARED.md` و تأیید اینکه `app/ai/model/ranker.joblib` در repo هست (برای README).

### اسکیما و دادههای مشترک
- ۹ جدول CONTRACT بخش ۷ — نام ستونها قطعی است؛ DEV-01 در services به همین نامها دسترسی دارد (مثلاً `request.sla_deadline_sim_min`، `dispatch.outcome`).
- مقادیر enum ستونها مطابق CONTRACT (مثلاً `outcome ∈ created|delivered|failed`).

---

## و) دستورالعمل دقیق پیادهسازی (گامبهگام)

1. **مخزن را بررسی کن:** `git status`؛ ساختار فعلی؛ `docs/CONTRACT.md` و `participant_kit/DATA_CARD.md` را بخوان؛ سرستون CSV ها را با `head -2` ببین (نامها مطابق CONTRACT بخش ۴ است).
2. **شاخه بساز:** `git switch -c feature/d02-data-layer master`. هرگز روی master کار نکن.
3. **ترتیب ساخت:**
   a. `requirements.txt` + `.gitignore` + `.env.example` (محیط زودتر آماده شود).
   b. `app/data/models.py` + `database.py`.
   c. `loader.py` — ابتدا donors/hospitals/centers/travel، بعد history bulk، بعد donor_events (defer محاسبه). **عملکرد را با time اندازه بگیر** (هدف: زیر ~۱۵ ثانیه کل بارگذاری).
   d. `repositories.py` — بهخصوص `DonorRepository.eligible` را با دقت روی قواعد فاصله اهدا و deferral بنویس.
   e. `tests/data/` همگام با هر مرحله.
   f. `scripts/setup|run|smoke` و تست از محیط تمیز.
   g. `README.md` و `DECLARED.md` (نسخه اولیه؛ تکمیل نهایی بعد از تستها).
4. **قواعد:** snake_case؛ بدون کامنت اضافی؛ بدون TODO؛ اعداد جادویی ممنوع (قواعد از `rules.yaml`، نه hard-code)؛ کوئریهای سنگین فقط با ایندکس؛ commit های کوچک انگلیسی.
5. **تست:** `python -m pytest tests/data -q` سبز؛ سپس smoke.
6. **PR:** rebase روی master، اجرای تستها، PR انگلیسی. چون لایه تو اولین merge است، reviewer (ثنا) سریع بررسی میکند تا بقیه روی آن بسازند.

---

## ز) الزامات تست

پوشه `tests/data/` (DB تستی = sqlite در حافظه یا فایل موقت؛ داده تست = زیرمجموعه کوچک CSV در فایلهای تست):

| فایل | پوشش | نتیجه مورد انتظار |
|---|---|---|
| `test_models.py` | ساخت همه جداول؛ قیود UNIQUE (idempotency_key، event_id، dispatch_id)؛ default ها | create_all موفق؛ INSERT تکراری → IntegrityError |
| `test_loader.py` | بارگذاری همه CSV ها؛ تعداد سطرها؛ **defer_until با قاعده آخرین رویداد** (دو رویداد tattoo با تاریخ متفاوت → فقط جدیدتر)؛ فایل غایب → خطای صریح؛ اندازهگیری زمان بارگذاری | شمارشها دقیق؛ fail-fast |
| `test_repositories.py` | هر ۸ ریپازیتوری: add_or_ignore تکراری → False؛ eligible با همه فیلترها (تعلیق فعال، سن خارج، وزن، فاصله اهدا، سکوت، ناسازگار، قبلاً دعوتشده)؛ history_features مقادیر صحیح؛ pop_due فقط وظایف موعدرسیده | همه پاس |
| `test_smoke_helpers.py` | توابع کمکی smoke (در صورت تفکیک) | — |

اجرا: `python -m pytest tests/data -q`. بعد از ساخت سرویس توسط DEV-01، معیار نهایی تو هم هست: `python scripts/smoke.py` از محیط تمیز (venv تازه) باید contract tests را سبز و P-normal را کامل اجرا کند.

---

## ح) معیارهای اتمام کار (چکلیست)

- [ ] همه فایلهای بخش «د» ساخته شدهاند؛ هیچ فایلی خارج از مالکیت تو تغییر نکرده است.
- [ ] نام جدولها/ستونها/توابع/کلاسها ۱۰۰٪ مطابق CONTRACT بخشهای ۷ و ۸.۱ است.
- [ ] بارگذاری کامل کیت (شامل ~۷۰۰هزار سطر history) زیر ~۱۵ ثانیه.
- [ ] `pytest tests/data -q` سبز (خروجی واقعی).
- [ ] `scripts/setup.ps1` و `scripts/run.ps1` از یک کلون تازه (پوشه موقت) با موفقیت اجرا شدهاند.
- [ ] `scripts/smoke.py` بعد از merge شدن لایه DEV-01 اجرا شده و خروجی دارد (contract سبز + نتیجه P-normal).
- [ ] `.env` در `.gitignore` است و `git status` آن را نشان نمیدهد.
- [ ] `README.md` و `DECLARED.md` فقط ادعاهای قابل نمایش دارند (هر قابلیت اعلامشده واقعاً تست شده).
- [ ] PR تو merge شده و master سالم است.
- [ ] موانع واقعی (در صورت وجود) صادقانه گزارش شدهاند.

---

## نکات عملیاتی نهایی برای عامل برنامهنویس

- تو **اولین merge** هستی — سرعت تو سرعت کل تیم است؛ اول مدلها و database را تمام کن (ساعت اول)، loader و repositories را بلافاصله بعد.
- بارگذاری bulk را با `sqlalchemy insert(...).values(rows)` در چند chunk انجام بده؛ از ORM تکتک برای ۷۰۰هزار سطر هرگز استفاده نکن.
- `defer_until` بهصورت رشته ISO ذخیره میشود؛ مقایسه در کوئری eligible باید بر حسب دقیقه شبیهسازی انجام شود (`sim_min` → تاریخ epoch + دقیقه). فرمول تبدیل: `sim_minutes_to_iso(epoch, sim_min)`؛ روزها: `sim_min / 1440`.
- ساعت محلی برای فیلتر سکوت: `hour = (epoch + sim_min دقیقه).hour` — همان ساعت محلی دادهها (بدون تبدیل UTC).
- اگر DEV-01 درخواست متد جدیدی در repositories داد، خودت اضافه کن (با تست) — او حق ویرایش فایلهای تو را ندارد.
- پیام commit انگلیسی؛ قبل از commit فقط فایلهای خودت را add کن.
- اگر تستی اجرا نشده، ادعای اجرا نکن؛ خروجیها را ضمیمه گزارش کن.

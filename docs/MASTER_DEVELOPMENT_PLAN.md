# سند اصلی توسعه پروژه — BloodNet

**نسخه:** 1.0 (تأییدشده) · **محدودیت:** ۶ ساعت ساخت · **تیم:** ۳ نفر
**مرجع قطعی نامها و قراردادها:** [docs/CONTRACT.md](CONTRACT.md) — هر چیزی که اینجا با CONTRACT.md تعارض داشت، CONTRACT.md ملاک است.

---

## ۱. خلاصه پروژه

BloodNet سرویس هماهنگی زنجیره تأمین خون یک استان ساختگی است: بیمارستان درخواست میدهد → موجودی مراکز با سازگاری و FEFO تخصیص مییابد → کسری از طریق دعوت هدفمند اهداکنندگان واجد شرایط (از طریق Gateway شبیهسازیشده) تأمین میشود → پاسخها و رویدادها بهصورت idempotent و مقاوم به بیترتیبی پردازش میشوند → وضعیت تأمین (کامل/ناقص) در هر لحظه صادقانه نمایش داده میشود.

معماری تأییدشده: **Modular Monolith + Layered + Hexagonal-lite** روی **FastAPI + SQLAlchemy/SQLite(WAL) + Vanilla JS**.

---

## ۲. ساختار کامل پوشهها و فایلها

```
SSApro/                                  ← ریشه مخزن (کیت مسابقه داخلش است)
├── participant_kit/                     ← داده و قرارداد کیت (فقطخواندنی — هیچکس ویرایش نمیکند)
├── harness/                             ← هارنس تمرینی (فقطخواندنی)
├── starter/                             ← کد نمونه کیت (مرجع، نه وابستگی)
├── app/
│   ├── __init__.py
│   ├── main.py                          [D01] ساخت FastAPI، lifespan (init DB + loader + dispatcher)،
│   │                                         نصب routers و StaticFiles، ساخت استراتژی رتبهبندی از تنظیمات
│   ├── config.py                        [D01] کلاس Settings (pydantic-settings) با کلیدهای CONTRACT بخش ۶
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py                      [D01] احراز هویت دو توکن (hospitalBearer / coordinatorBearer)
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── health.py                [D01] GET /health
│   │       ├── requests.py              [D01] POST /requests، GET /requests/{id}، amend، cancel، approve
│   │       ├── callbacks.py             [D01] سه callback
│   │       └── ui.py                    [D01] endpoint های /api/* (CONTRACT بخش ۹)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── state_machine.py             [D01] گذرگاههای وضعیت + InvalidTransitionError
│   │   └── ranking.py                   [D01] Protocol و dataclassهای رتبهبندی
│   ├── services/
│   │   ├── __init__.py
│   │   ├── request_service.py           [D01] create/idempotency/amend/cancel/approve/get
│   │   ├── allocation_service.py        [D01] FEFO + سازگاری + dispatch اتمی
│   │   ├── invitation_service.py        [D01] پیشفیلتر واجدین + موجها + توقف + استراتژی پیشفرض travel_time
│   │   ├── callback_processor.py        [D01] dedup و شمارندهها (۳ نوع callback)
│   │   └── sla_service.py               [D01] بررسی انقضای SLA
│   ├── ports/
│   │   ├── __init__.py
│   │   └── clients.py                   [D01] ClockClient/GatewayClient/InventoryClient/TravelClient + retry
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── dispatcher.py                [D01] حلقه پسزمینه asyncio روی جدول tasks + sla + تحویل موجودی
│   ├── data/
│   │   ├── __init__.py
│   │   ├── database.py                  [D02] engine/SQLite WAL/session
│   │   ├── models.py                    [D02] ۹ جدول CONTRACT بخش ۷
│   │   ├── repositories.py              [D02] ۸ ریپازیتوری CONTRACT بخش ۸.۱
│   │   └── loader.py                    [D02] بارگذاری CSVها + yamlها + bulk history + محاسبه defer_until
│   └── ai/
│       ├── __init__.py
│       ├── ranking.py                   [D03] AIResponseRankingStrategy (پیادهسازی Protocol)
│       └── model/                       [D03] ranker.joblib + scaler + feature_config.json (commit میشود)
├── static/                              [D03] رابط کاربری (سرو توسط FastAPI روی :8000)
│   ├── index.html                       نمای کارمند بیمارستان
│   ├── center.html                      نمای کارمند مرکز
│   ├── donor.html                       جریان تعامل اهداکننده (دمو)
│   ├── css/styles.css
│   └── js/
│       ├── apiClient.js                 fetch wrapper + توکن + نگاشت خطاها به فارسی
│       ├── hospitalView.js
│       ├── centerView.js
│       └── donorView.js
├── scripts/
│   ├── setup.ps1 / setup.sh             [D02] venv + نصب requirements
│   ├── run.ps1 / run.sh                 [D02] اجرای یکدستوری سرویس
│   ├── smoke.py                         [D02] اجرای خودکار contract_tests + سناریو P-normal + چاپ خلاصه
│   ├── train_model.py                   [D03] آموزش مدل محلی از history
│   └── evaluate_model.py                [D03] ارزیابی عددی مدل (مستندسازی C1)
├── tests/
│   ├── core/                            [D01] تست واحد+یکپارچگی هسته
│   ├── data/                            [D02] تست لایه داده
│   ├── ai/                              [D03] تست ماژول هوشمند
│   └── e2e/                             [D01] تست سرتاسری
├── docs/
│   ├── CONTRACT.md                      قرارداد مشترک (FROZEN)
│   ├── MASTER_DEVELOPMENT_PLAN.md       همین سند
│   ├── DEVELOPER_01_BACKEND_CORE_IMPLEMENTATION_GUIDE.md
│   ├── DEVELOPER_02_BACKEND_DATA_IMPLEMENTATION_GUIDE.md
│   ├── DEVELOPER_03_FRONTEND_AI_IMPLEMENTATION_GUIDE.md
│   ├── INTEGRATION_GUIDE.md
│   ├── DEFENSE_QA_GUIDE.md
│   └── ai_module.md                     [D03] مستندات ماژول هوشمند برای DECLARED.md
├── README.md                            [D02] راهنمای اجرا/دمو
├── DECLARED.md                          [D02] اعلام رسمی قابلیتها برای داوران
├── .env.example                         [D02]
├── .gitignore                           [D02]
└── requirements.txt                     [D02]
```

### مسئولیت ماژولها (خلاصه)

| ماژول | هدف | وابستگی |
|---|---|---|
| `app/api` | نقطه ورود قرارداد رسمی + UI؛ اعتبارسنجی Pydantic و کدهای خطا | services, ports |
| `app/services` | تمام منطق کسبوکار (درخواست، تخصیص، دعوت، callback) | domain, data(repositories), ports |
| `app/domain` | قواعد خالص بدون I/O (ماشین وضعیت، Protocol رتبهبندی) | هیچ |
| `app/ports` | تنها مسیر تماس با ۴ سرویس کیت؛ retry/timeout | هیچ (httpx) |
| `app/data` | مدلها، اتصال DB، بارگذاری کیت، کوئریها | هیچ (SQLAlchemy) |
| `app/tasks` | حلقه پسزمینه مصرفکننده جدول tasks | services, ports |
| `app/ai` | استراتژی رتبهبندی مبتنی بر مدل محلی | domain (Protocol) |
| `static` | سه نمای UI با polling | /api/* و مسیرهای رسمی |

قاعده وابستگی: فقط رو به پایین (api→services→domain/data)؛ services فقط از طریق repositories به DB؛ هیچکس جز ports با سرویسهای کیت حرف نمیزند.

---

## ۳. استاندارد نامگذاری

| بستر | قانون | مثال |
|---|---|---|
| پایتون: ماژول/تابع/متغیر | `snake_case` | `build_wave`، `sla_deadline_sim_min` |
| پایتون: کلاس | `PascalCase` | `RequestService` |
| پایتون: ثابت | `UPPER_SNAKE` | `WAVE_MAX_SIZE` |
| JS: تابع/متغیر | `camelCase` | `loadRequests` |
| JS/HTML/CSS: فایل | `camelCase` | `hospitalView.js` |
| جداول/ستونهای DB | `snake_case`، جداول جمع | `dispatches` |
| مقدار enum/فیلد JSON | دقیقاً مطابق CONTRACT (انگلیسی) | `red_cells`، `partially_fulfilled` |
| branch | `feature/d01-...` | `feature/d02-data-layer` |
| commit | `type(scope): summary` انگلیسی | `feat(requests): idempotent create` |
| متن UI | فارسی RTL | — |

---

## ۴. اعضای تیم و مرزبندی وظایف

| شناسه | عضو | نقش | مالکیت | خارج از محدوده |
|---|---|---|---|---|
| **DEV-01** | ثنا | Backend Core / Lead | `app/api`, `app/domain`, `app/services`, `app/ports`, `app/tasks`, `app/main.py`, `app/config.py`, `tests/core`, `tests/e2e` | فایلهای data، static، ai، اسناد |
| **DEV-02** | اسرا | Backend Data & Delivery | `app/data`, `requirements.txt`, `.gitignore`, `.env.example`, `scripts/` (بهجز train/evaluate مدل), `README.md`, `DECLARED.md`, `tests/data` | services، routers، static، ai |
| **DEV-03** | شقایق | Frontend + AI | `static/`, `app/ai/`, `scripts/train_model.py`, `scripts/evaluate_model.py`, `tests/ai`, `docs/ai_module.md` | backend، data، اسناد تیم |

هر عضو فقط فایل اختصاصی خودش را از [docs/](.) میگیرد و آن را به عامل AI میدهد — فایلها کاملاً مستقل و بدون نیاز به مکالمات قبلیاند.

---

## ۵. قراردادهای ارتباطی (خلاصه)

جزئیات کامل در [docs/CONTRACT.md](CONTRACT.md). نکات حیاتی:

- **قرارداد رسمی**: ۹ مسیر API (بخش ۲.۱ CONTRACT) با Schemaها و کدهای خطای قطعی؛ `idempotency_key_reuse` دقیقاً همین رشته.
- **سرویسهای کیت**: فقط از `app/ports`؛ فرمت پیام Gateway با ۵ قالب قطعی؛ dispatch با `dispatch_id` idempotent.
- **UI داخلی**: ۹ مسیر `/api/*` + DTOهای `RequestDetail` و `DonorInvitation` — فرانت فقط از این قرارداد استفاده میکند.
- **داخل بکاند**: امضای توابع بخش ۸ CONTRACT — DEV-02 متدها را با همین نامها میسازد، DEV-01 با همین نامها مصرف میکند، DEV-03 فقط Protocol رتبهبندی را پیاده میکند.
- **DB**: ۹ جدول بخش ۷ CONTRACT.
- **احراز هویت**: دو توکن از env؛ hospital برای ثبت/مشاهده/اصلاح/لغو و `/api/*` (بهجز inventory/centers)، coordinator برای approve و inventory/centers، callbacks بدون auth.

---

## ۶. مدیریت Git (فرایند کامل)

**مخزن:** `https://github.com/ISanaSaki/SSApro.git` (remote `origin`)

1. **انشعاب اصلی:** `master` (شاخه واقعی مخزن — همیشه سالم و قابل اجرا). هیچ commit مستقیمی روی master نمیرود.
2. **Feature branch:** هر نفر از آخرین master:
   ```bash
   git switch master && git pull && git switch -c feature/d01-state-machine
   ```
3. **Commit اتمی و انگلیسی** (Conventional Commits): بعد از هر واحد منطقی قابل تست. هرگز `git add .` — فقط فایلهای مرتبط و متعلق به خودش؛ قبل از هر commit، `git status` بازبینی شود.
4. **Pull Request:** قبل از PR، rebase فقط روی شاخه feature خودش و اجرای تستهای خودش. PR کوچک و تکموضوعی. Squash merge فقط با تأیید reviewer.
5. **Review:** ثنا reviewer همه PRها (نقش Backend Lead)؛ PRهای ثنا را اسرا review میکند؛ شقایق بخش UI را هم خودش sanity-check میکند. معیار merge: تستها سبز + عدم تداخل با نقشه مالکیت + احترام به CONTRACT.
6. **تعارض:** هر تعارض در فایلهای مشترک فقط در جلسه یکپارچهسازی (ساعت ۵) با حضور صاحبان فایلها حل میشود؛ اولویت با CONTRACT.md است. **هر Conflict احتمالی باید پیش از اقدام گزارش شود.**
7. **عملیات مخرب ممنوع:** Reset، Rebase شاخه مشترک، Force Push، حذف/دستکاری شاخه یا تغییرات commitنشده دیگران — بدون اجازه صریح صاحب کار. هر عضو فقط تغییرات خودش را commit میکند.
8. **گزارش پیش از کدنویسی:** هر عضو قبل از نوشتن اولین خط کد، گزارش کوتاه (محدوده وظایف، فایلهای مجاز، وابستگیها، ریسکها) ارائه میدهد و تا تأیید محدوده، پیادهسازی را شروع نمیکند.
9. **محرمانه:** `.env` هرگز commit نمیشود؛ `.env.example` شامل توکنهای دموی کیت است (راز واقعی وجود ندارد).
10. **ترتیب merge:** d02 (لایه داده) → d01 (هسته) → d03 (UI) → d03 (AI) — چون هر لایه به لایه قبلی وابسته است (جزئیات در INTEGRATION_GUIDE).

---

## ۷. راهبرد تست

| سطح | مالک | ابزار | پوشش |
|---|---|---|---|
| واحد | D01/D02/D03 | pytest (+pytest-asyncio) | ماشین وضعیت، واجدین، FEFO، dedup، loader، استراتژیها |
| یکپارچگی | D01 | pytest + httpx ASGITransport + mock ports | قرارداد کامل API، idempotency همزمان (۲۰ تایی)، callback نامرتب/تکراری |
| e2e | D01 | اسکریپت + هارنس واقعی | contract_tests + سناریوهای P-normal/P-amend/P-abuse |
| داده | D02 | pytest | بارگذاری ۷۰۰هزار سطر، latest-event-wins، ریپازیتوریها |
| AI | D03 | pytest | ورودی/خروجی، بازه [0,1]، fallback |
| دستی UI | D03 | مرورگر | چکلیست ۳ نما (در guide او) |

فرمان استاندارد: `python -m pytest tests/ -q` از ریشه مخزن؛ قبل از هر merge الزامی است.
شواهد نهایی (برای DECLARED): idempotency، سازگاری، لغو، callback تکراری/همزمان، safety (صفر اعلان به معلقین).

---

## ۸. برنامه زمانی ۶ ساعته و ترتیب پیادهسازی

| بازه | کار | مالک |
|---|---|---|
| 00:00–00:30 | خواندن guide ها + CONTRACT؛ ساخت branchها؛ **فریز قرارداد**؛ setup محیط؛ گزارش کوتاه محدوده/وابستگی/ریسک هر عضو | همه |
| 00:30–01:30 | لایه داده کامل + تستهایش + اسکریپت اجرا | D02 |
| 00:30–02:30 | ماشین وضعیت + schemas + config + ports (مستقل از data) | D01 |
| 01:30–04:00 | request/allocation/invitation/callback + routers رسمی + تستهای هسته (روی لایه داده D02) | D01 |
| 00:30–03:00 | طراحی و پیادهسازی سه نمای UI (با mock اولیه، سپس API واقعی) | D03 |
| 03:00–05:00 | ماژول AI (آموزش مدل، استراتژی، ارزیابی) + اتصال به UI | D03 |
| 04:00–04:30 | اتصال استراتژی AI در master + e2e ابتدایی | D01+D03 |
| 04:30–05:15 | README/DECLARED + smoke + اجرای هر ۳ سناریوی تمرینی + رفع اشکال | D02 + همه |
| 05:15–05:45 | یکپارچهسازی نهایی (INTEGRATION_GUIDE)، بازبینی safety، تست از محیط تمیز | همه |
| 05:45–06:00 | دموی کامل، commit نهایی، push | همه |

**قاعده طلایی اولویتبندی:** P0 (idempotency/تخصیص اتمی/callback/ساعت/تعلیق/تقلب/تحویلدادنیها) → P1 (چرخه کامل، SLA، کنترل spam/overfill، UI) → P2 → P3. «کم اما کامل» همیشه بر «زیاد اما ناقص» مقدم است. ماژول AI فقط وقتی شروع میشود که UI و هسته سالم باشند.

---

## ۹. مدیریت ریسک (خلاصه از سند معماری)

| ریسک | راهکار |
|---|---|
| صفر شدن امتیاز با safety gate (اعلان به معلق) | پیشفیلتر سختگیرانه در invitation + تست اختصاصی همه حالتهای تعلیق + بازبینی دو نفره |
| گلوگاه SQLite زیر بار ۱۲۸ worker | WAL + busy_timeout + کوئریهای کوتاه + ایندکس + تست بار |
| تمام شدن وقت | اولویتبندی P0→P1؛ هر قابلیت یا کامل است یا در DECLARED اعلام نمیشود |
| تناقض اسناد کیت (units 20/10 و نام وضعیت open/active) | قرارداد رسمی openapi ملاک است: units 1..20 و وضعیت `open` (در CONTRACT قفل شده) |
| Overfill/spam در کالیبراسیون مخفی | هیچ عددی hard-code نیست؛ همه سقفها از env (CONTRACT بخش ۶) |
| ریاستارت و از دست رفتن وظایف | وظایف در جدول tasks ماندگارند و در startup re-drive میشوند |

---

## ۱۰. الزامات تحویل (F15 — همه مسئول، مالک نهایی D02)

- `README.md`: اجرای یکدستوری از محیط تمیز (setup + run + دمو).
- `DECLARED.md`: فهرست صادقانه قابلیتها (فقط چیزهایی که واقعاً کار میکنند).
- مستند معماری (همین سند + CONTRACT).
- مسیر دموی تکرارپذیر: `scripts/smoke.py` + سه نمای UI.
- شواهد تست: خروجی pytest + نتایج سه سناریوی تمرینی در `docs/` یا خروجی smoke.
- آخرین commit قبل از مهلت = تحویل.

---

## ۱۱. فرضیات صریح (در صورت ابهام در حین کار)

1. قرارداد رسمی openapi.yaml بر starter مقدم است (units تا ۲۰، وضعیت `open`).
2. `X-Sim-Time` فقط اطلاعاتی است؛ مبنای منطق `ClockClient` است.
3. درخواستهای ثبتنشده (H98) بلافاصله 400 میشوند (سیاست قطعی بخش ۵.۱ CONTRACT).
4. ساعات سکوت محافظهکارانه رعایت میشود (در بازه سکوت ارسال نمیشود).
5. امتیاز تمرینی فقط سیگنال است؛ هیچ عددی hard-code نمیشود.
6. UI الزامی است (۳۰ امتیاز) و مسیرهای `/api/*` فقط برای UI هستند و قرارداد رسمی را لمس نمیکنند.

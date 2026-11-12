# DEVELOPER_03_FRONTEND_AI_IMPLEMENTATION_GUIDE.md

**این فایل را کامل بخوان، سپس شروع کن.** تو یک عامل برنامهنویسی هستی و این سند تمام اطلاعات لازم برای پیادهسازی بخش تو را دارد. نیازی به هیچ مکالمه یا سند دیگری نداری (مگر برای جزئیات بیشتر به `docs/CONTRACT.md` در همین مخزن رجوع کنی که منبع نهایی نامهاست).

---

## الف) مشخصات و هویت توسعهدهنده

| مورد | مقدار |
|---|---|
| شناسه عضو | **DEV-03** |
| عضو تیم | شقایق (Frontend + AI) |
| نقش اختصاصی | سه رابط کاربری (Vanilla JS) + ماژول هوشمند محلی رتبهبندی اهداکنندگان |
| مسئولیت اصلی | `static/**`، `app/ai/**`، `scripts/train_model.py`، `scripts/evaluate_model.py`، `tests/ai/**`، `docs/ai_module.md` |
| محدوده دقیق وظایف | تمام فایلهای فهرست بخش «د» |
| **خارج از محدوده** | تمام بکاند (`app/api`، `app/services`، `app/domain`، `app/ports`، `app/tasks`، `app/data`، `app/main.py`، `app/config.py` — مال DEV-01 و DEV-02)؛ `README.md`/`DECLARED.md`/`scripts/setup|run|smoke` (مال DEV-02). **هرگز این فایلها را ویرایش نکن.** فقط تو `Protocol` رتبهبندی (که DEV-01 در `app/domain/ranking.py` تعریف کرده) را **import و پیادهسازی** میکنی. |

---

## ب) معرفی پروژه و اطلاعات موردنیاز

### مسئله
در یک استان ساختگی، بیمارستانها درخواست فرآورده خونی میدهند؛ سرویس BloodNet موجودی مراکز را (سازگار و FEFO) تخصیص میدهد، کسری را محاسبه میکند و اهداکنندگان واجد شرایط را از طریق Gateway شبیهسازیشده دعوت میکند. داوران ۳۰ امتیاز به کیفیت رابط کاربری و تا +۲۰ امتیاز به ماژول هوشمند محلی میدهند.

### معماری (تأییدشده)
**Modular Monolith**: یک فرایند FastAPI روی `:8000` که فایلهای استاتیک تو را هم سرو میکند. فرانت **Vanilla JS (ES Modules) بدون build step** است و فقط با API های همان سرویس (base URL نسبی) حرف میزند — بدون CORS، بدون artifact. ماژول هوشمند یک **استراتژی رتبهبندی** است که از طریق Protocol مشترک (`DonorRankingStrategy` در `app/domain/ranking.py` که DEV-01 میسازد) به موتور دعوت وصل میشود.

### فناوریهای بخش تو
HTML/CSS/Vanilla JS (ES Modules) · RTL فارسی · (اختیاری Figma برای طراحی اولیه) · Python: pandas + scikit-learn + joblib (مدل محلی — شرط مسابقه: کاملاً محلی، بدون سرویس پولی/کلید/ابر).

### جایگاه بخش تو در کل برنامه
- **فرانت:** تنها پنجره کاربر به محصول؛ معیار داوری: «وضوح جریان کار، نمایش صادقانه اعداد، واکنشگرایی، اتصال صحیح به بکاند». اعداد باید همیشه از API بیایند — هرگز client-side ساخته نشوند.
- **AI:** امتیاز افزوده (C1)؛ فقط وقتی کامل و قابل ارزیابی عددی باشد در DECLARED اعلام میشود. خروجی تو مستقیماً معیار spam را بهبود میدهد (دعوت هدفمندتر = پیام کمتر بهازای هر واحد تأمینشده).

---

## ج) شرح دقیق وظایف اجرایی

### T1 — زیرساخت مشترک فرانت (`static/js/apiClient.js`)

- fetch wrapper: `apiRequest(method, path, {tokenKey, body}) -> Promise<json>` با base URL نسبی (همان origin).
- توکنها از `localStorage`: کلیدهای قطعی `bloodnet_hospital_token` و `bloodnet_coordinator_token`؛ هدر `Authorization: Bearer <token>`.
- رفتار خطا: هر پاسخ `{"error":{"code","message"}}` → throw شیء `{code, message}`؛ نگاشت code به پیام فارسی در جدول `ERROR_MESSAGES` (کدهای CONTRACT بخش ۲.۳: `unauthorized` → «توکن نامعتبر است»، `not_found` → «درخواست یافت نشد»، `idempotency_key_reuse` → «کلید تکراری با بدنه متفاوت»، `validation_error` → «مقادیر نامعتبر»، `unknown_hospital` → «بیمارستان ثبتنشده»، `not_amendable`/`not_approvable` → «وضعیت فعلی اجازه این عملیات را نمیدهد»، `internal_error` → «خطای داخلی سرویس»).
- توابع کمکی: `getClock()` (GET `/api/clock`)، `poll(fn, intervalMs)`، `formatSimMinutes(min)` (نمایش «روز/ساعت/دقیقه شبیهسازی»)، `toast(msg, type)`.
- تمام شناسهها/مقادیر انگلیسی؛ متنهای نمایشی فارسی.

### T2 — نمای بیمارستان (`static/index.html` + `static/js/hospitalView.js`)

- **هدر:** ورودی توکن بیمارستان (localStorage) + انتخاب بیمارستان (dropdown از `GET /api/hospitals`) + نمایش ساعت شبیهسازی (polling از `/api/clock` هر ۵ ثانیه).
- **فرم ثبت درخواست:** dropdown ها با مقادیر دقیق enums: `blood_group ∈ [O+, A+, B+, AB+, O-, A-, B-, AB-]`، `product ∈ [red_cells, platelets, plasma]`، `urgency ∈ [critical, urgent, planned]`، `units` عدد 1..20، `note` اختیاری (≤500). ارسال → `POST /requests` با هدر `Idempotency-Key: crypto.randomUUID()` و `Authorization: Bearer <hospital_token>`. موفقیت → نمایش request_id و رفتن به جزئیات.
- **لیست درخواستها:** `GET /api/requests?hospital_id=<انتخابشده>` هر ۵ ثانیه؛ کارت هر درخواست: request_id، گروه/محصول/واحدها، badge وضعیت (نگاشت فارسی: pending_review→در انتظار تأیید، open→باز، mobilizing→در حال بسیج، partially_fulfilled→تأمین ناقص، fulfilled→تأمین کامل، cancelled→لغوشده، expired→منقضی)، نوار پیشرفت `fulfilled/needed`.
- **جزئیات درخواست:** `GET /api/requests/{id}` هر ۳ ثانیه؛ شمارندهها (needed/confirmed/en_route/arrived/fulfilled/stock_inflight/shortage)، شمارش معکوس SLA (`sla_deadline_sim_min - sim_min`)، جدول dispatches، خط زمانی events (جدیدترین اول).
- **عملیات:** دکمه اصلاح فوریت (modal با سه گزینه → `POST /requests/{id}/amend`)، دکمه لغو با confirm (`POST /requests/{id}/cancel`) — هر دو با توکن بیمارستان؛ خطاها toast.
- **قاعده صداقت:** اگر shortage > 0 نمایش «کسری: X واحد»؛ هرگز عددی محاسبه و نمایش نده که از API نیامده.

### T3 — نمای مرکز (`static/center.html` + `static/js/centerView.js`)

- **هدر:** ورودی توکن هماهنگکننده (`bloodnet_coordinator_token`) + ساعت شبیهسازی.
- **صف تأیید:** `GET /api/requests?status=pending_review` (توکن coordinator) → کارت با دکمه «تأیید» (`POST /requests/{id}/approve` با body `{"approved": true}`) و «رد» (`{"approved": false}`).
- **نمای کلی درخواستها:** `GET /api/requests` با فیلتر وضعیت (dropdown)؛ همان کارتها + تأکید بر shortage.
- **موجودی زنده:** `GET /api/inventory` هر ۵ ثانیه → جدول `center_id, blood_group, product, units, expires_sim_min` با هایلایت واحدهای رو به انقضا (کمتر از `shelf_days[product] * 0.2` دقیقه باقیمانده) — فقط نمایش، بدون تصمیمگیری.
- **KPI ها (فقط از داده API):** تعداد درخواستهای فعال، مجموع fulfilled، مجموع shortage.

### T4 — جریان اهداکننده (دمو) (`static/donor.html` + `static/js/donorView.js`)

- ورودی `donor_id` + دکمه «دریافت دعوتهای من» → `GET /api/donor/invitations?donor_id=`.
- هر دعوت: کارت با request_id/محصول/گروه/وضعیت؛ دکمههای «میپذیرم» / «رد میکنم» → `POST /api/donor/respond` با `{"donor_id","request_id","response"}`.
- بعد از پذیرش، دکمههای پیشرفت: `en_route`، `arrived`، `screen_pass`، `screen_fail`، `donated`، `no_show` → `POST /api/donor/progress` با `{"donor_id","request_id","event"}`.
- راهنما روی صفحه: این صفحه شبیهساز رفتار اهداکننده برای دمو است؛ در ارزیابی واقعی همین رویدادها توسط هارنس ارسال میشوند.
- بعد از هر اقدام: refresh دعوتها + نمایش toast نتیجه.

### T5 — استایل (`static/css/styles.css`)

- RTL، فونت سیستم فارسی (Vazirmatn از CDN ممنوع است — آفلاین! از فونتهای سیستمی مثل `Segoe UI, Tahoma` استفاده کن)، چیدمان responsive (موبایل/دسکتاپ)، تم تیره ملایم پزشکی (قرمز خون بهعنوان رنگ تأکید)، badgeهای رنگی برای ۷ وضعیت، جدولها با overflow افقی. بدون هیچ وابستگی خارجی (CDN/آیکون آنلاین ممنوع — همهچیز محلی).

### T6 — ماژول هوشمند محلی (`app/ai/ranking.py`)

- کلاس `AIResponseRankingStrategy` با `name = "ai_response"` که `DonorRankingStrategy` را از `app/domain/ranking.py` پیاده میکند (import از مسیر `app.domain.ranking`).
- سازنده: `__init__(self, model_path: str)` — بارگذاری `ranker.joblib` + scaler + `feature_config.json` از `app/ai/model/`؛ اگر فایل نبود → پرچم `available=False` و log هشدار (fallback).
- `rank(donors, context) -> list[RankedDonor]`: ساخت ویژگیها برای هر donor (فهرست T7) → `predict_proba` → `score = P(accepted)`؛ `travel_minutes` از `context.travel_minutes`؛ خروجی مرتب نزولی بر اساس score، تساویشکن صعودی travel. اگر مدل در دسترس نبود → score = -travel (معادل رتبهبندی زمانی) — **هرگز exception نده.**
- **قواعد الزامی مسابقه:** فقط کتابخانههای محلی؛ ورودی = ویژگیهای عددی اهداکننده؛ خروجی = عدد 0..1؛ بدون هیچ سرویس خارجی/کلید/API.

### T7 — آموزش مدل (`scripts/train_model.py`)

- **منابع داده:** `participant_kit/donors.csv` (ویژگیهای پایه) + `participant_kit/history/responses.csv` (برچسب) — خواندن با pandas.
- **ویژگیهای قطعی (feature_config.json):** `age`، `sex` (M→0/F→1)، `weight_kg`، `blood_group` (one-hot ۸ گروه)، `notified_90d`، `days_since_last_donation` (از `last_donation_at`؛ خالی → 999)، `last_donation_type` (one-hot)، `quiet_window_len` (ساعت)، و از history بهازای هر donor: `hist_notified`، `hist_responded`، `hist_accepted`، `hist_donated`، `accept_rate`، `donate_rate`، `mean_response_delay_min`، `days_since_last_notified`.
- **برچسب:** `accepted` از history/responses.csv (فقط سطرهای `responded==1`).
- **مدل:** `sklearn.pipeline.Pipeline([StandardScaler(), LogisticRegression(max_iter=1000)])` — سریع، کوچک، تفسیرپذیر (در دفاع قابل توضیح). خروجی: `app/ai/model/ranker.joblib` + `scaler` داخل pipeline + `feature_config.json` (نام و ترتیب ویژگیها). این فایلها **commit** میشوند (دمو باید بدون آموزش مجدد اجرا شود).
- **محدودیت مستند:** مدل روی داده تاریخی (رفتار گذشته) آموزش دیده؛ در docs/ai_module.md بنویس که پیشبینی «احتمال پذیرش» است نه تصمیم پزشکی.

### T8 — ارزیابی عددی (`scripts/evaluate_model.py` + `docs/ai_module.md`)

- `evaluate_model.py` دو خروجی عددی چاپ میکند:
  1. **Holdout:** تقسیم 80/20 بر اساس donor_id؛ متریکها: `AUC`، `precision@k` (k=20) — با sklearn.
  2. **شبیهسازی تاریخی:** روی ۲۰۰ درخواست نمونه history، مقایسه «میانگین پیام بهازای هر پذیرش» بین رتبهبندی `travel_time` و `ai_response` (شبیهسازی ساده wave با سقف ۲۴) — عدد کمتر = بهتر (مستقیم متناظر با معیار spam).
- `docs/ai_module.md`: ورودی/خروجی، روش ارزیابی، محدودیتها (سوگیری داده تاریخی، ساختگی بودن داده)، نحوه فعالسازی (`RANKING_STRATEGY=ai_response` در `.env`)، fallback خودکار. این سند را به DEV-02 بده تا در DECLARED.md ادغام کند.
- **فعالسازی در محصول:** فقط env؛ تو کد DEV-01 را تغییر نمیدهی — او بر اساس `RANKING_STRATEGY` استراتژی تو را import میکند.

---

## د) فایلهایی که باید ایجاد یا ویرایش شوند

| مسیر | مسئولیت |
|---|---|
| `static/index.html` | نمای بیمارستان (RTL فارسی) |
| `static/center.html` | نمای مرکز |
| `static/donor.html` | جریان اهداکننده (دمو) |
| `static/css/styles.css` | استایل مشترک |
| `static/js/apiClient.js` | fetch wrapper + خطاها + polling |
| `static/js/hospitalView.js` | منطق نمای بیمارستان |
| `static/js/centerView.js` | منطق نمای مرکز |
| `static/js/donorView.js` | منطق نمای اهداکننده |
| `app/ai/__init__.py` | — |
| `app/ai/ranking.py` | `AIResponseRankingStrategy` |
| `app/ai/model/ranker.joblib` + `feature_config.json` | آرتیفکت مدل (commit میشود) |
| `scripts/train_model.py` | آموزش + ذخیره مدل |
| `scripts/evaluate_model.py` | ارزیابی عددی |
| `tests/ai/` | تستهای ماژول (بخش ز) |
| `docs/ai_module.md` | مستندات C1 برای DECLARED |

---

## هـ) قراردادهای ارتباطی با سایر بخشها

### APIهایی که مصرف میکنی (قطعی — DEV-01 دقیقاً همین را پیاده میکند)

**رسمی (نیازمند توکن):**
| Method | Path | توکن | بدنه |
|---|---|---|---|
| POST | `/requests` | hospital | `{hospital_id, blood_group, product, units, urgency, note?}` + هدر `Idempotency-Key` |
| GET | `/requests/{id}` | hospital | — |
| POST | `/requests/{id}/amend` | hospital | `{urgency}` |
| POST | `/requests/{id}/cancel` | hospital | `{}` |
| POST | `/requests/{id}/approve` | coordinator | `{approved, note?}` |

**داخلی UI (مطابق CONTRACT بخش ۹):**

| Method | Path | توکن | ورودی | خروجی |
|---|---|---|---|---|
| GET | `/api/requests` | hospital/coordinator | `?hospital_id=&status=` | `{"requests": [RequestDetail]}` |
| GET | `/api/requests/{id}` | hospital/coordinator | — | `RequestDetail` |
| GET | `/api/inventory` | coordinator | — | `{"sim_time","items":[{center_id,blood_group,product,units,expires_at,expires_sim_min}]}` |
| GET | `/api/hospitals` | hospital | — | `{"hospitals":[{hospital_id,name}]}` |
| GET | `/api/centers` | coordinator | — | `{"centers":[{center_id,name}]}` |
| GET | `/api/clock` | ندارد | — | `{"sim_time","epoch","speed"}` |
| GET | `/api/donor/invitations?donor_id=` | ندارد | query | `{"donor_id","invitations":[DonorInvitation]}` |
| POST | `/api/donor/respond` | ندارد | `{donor_id,request_id,response}` | `{"ok":true}` |
| POST | `/api/donor/progress` | ندارد | `{donor_id,request_id,event}` | `{"ok":true}` |

### `RequestDetail` (قالب قطعی)

```json
{
  "request_id": "R-ab12cd34ef56", "status": "mobilizing",
  "hospital_id": "H07", "blood_group": "O+", "product": "red_cells",
  "units": 8, "urgency": "critical", "note": null,
  "needed": 8, "confirmed": 5, "en_route": 3, "arrived": 2,
  "fulfilled": 3, "stock_inflight": 2, "shortage": 3,
  "created_sim_min": 123.4, "updated_sim_min": 150.0,
  "sla_deadline_sim_min": 213.4, "sim_min": 152.0, "wave_count": 2,
  "events": [{ "event_id", "kind", "donor_id", "notification_id", "response", "event", "status", "reason", "sim_time" }],
  "dispatches": [{ "dispatch_id", "request_id", "center_id", "blood_group", "product", "units", "hospital_id", "recipient_blood_group", "created_sim_min", "delivery_sim_min", "outcome" }]
}
```

### `DonorInvitation`

```json
{ "notification_id": "nt-...", "request_id": "R-...", "template": "request_wave",
  "created_sim_min": 130.0, "gateway_status": "delivered", "response": null, "event": null }
```

### رابطی که از بکاند import میکنی (فقط همین — به هیچ فایل بکاند دیگری دست نزن)

```python
# app/domain/ranking.py (ساخته DEV-01)
from app.domain.ranking import DonorRankingStrategy, RankedDonor, RankingContext
# تو فقط این Protocol را پیاده میکنی:
#   name: str
#   rank(donors, context: RankingContext) -> list[RankedDonor]
```

### قراردادهای پایگاه داده (فقط برای اسکریپتهای آموزش)
جداول و ستونها در CONTRACT بخش ۷؛ تو در train/evaluate مستقیم از CSV ها میخوانی (نه DB) — `donors.csv` و `history/responses.csv` با ستونهای CONTRACT بخش ۴.

---

## و) دستورالعمل دقیق پیادهسازی (گامبهگام)

1. **مخزن را بررسی کن:** `git status`؛ `docs/CONTRACT.md` را بخوان؛ `participant_kit/DATA_CARD.md` و دو CSV (donors، history/responses) را ببین؛ مسیر `static/` را بساز.
2. **شاخه بساز:** `git switch -c feature/d03-frontend master` (و بعداً `feature/d03-ai`). هرگز روی master کار نکن.
3. **ترتیب:**
   a. طراحی سریع سه نما (کاغذی/Figma اختیاری) بر اساس چکلیست T2–T4.
   b. `apiClient.js` + `styles.css` (زیرساخت).
   c. `hospitalView.js` → `centerView.js` → `donorView.js`؛ در نبود بکاند، با `fetch` mock موقت در کنسول تست کن ولی **هیچ mock ای commit نکن** — قرارداد بالا قطعی است و DEV-01 همان را میسازد.
   d. بعد از بالا آمدن بکاند: تست واقعی سه نما در مرورگر (گام طلایی + حالتهای خطا: توکن غلط، hospital ناشناخته، amend روی fulfilled).
   e. `train_model.py` → اجرا → آرتیفکت → `ranking.py` → `evaluate_model.py` → `docs/ai_module.md`.
   f. `tests/ai/` + اجرا.
4. **قواعد:** JS camelCase؛ فایلهای camelCase؛ بدون کتابخانه/CDN خارجی؛ بدون build step؛ متن فارسی فقط در HTML/JS استرینگها؛ همه مقادیر enum انگلیسی؛ اعداد فقط از API.
5. **تست مرورگر واقعی:** هر سه صفحه را با سرویس در حال اجرا باز کن؛ سناریوی کامل دمو را کلیک کن (ثبت درخواست → مشاهده تأیید/تخصیص → دعوت → donated → fulfilled).
6. **PR:** rebase روی master؛ commit های انگلیسی `feat(ui): ...` / `feat(ai): ...`؛ فقط فایلهای خودت.

---

## ز) الزامات تست

### تستهای خودکار (`tests/ai/`)

| فایل | پوشش | نتیجه مورد انتظار |
|---|---|---|
| `test_ranking.py` | ساخت استراتژی با مدل واقعی (آرتیفکت)؛ `rank` خروجی مرتب نزولی با score در [0,1]؛ خروجی شامل همه donorها؛ مدل غایب → بدون exception و fallback زمانی | همه پاس |
| `test_features.py` | ساخت ویژگیها از نمونه کوچک donors/history: مقادیر عددی، one-hot صحیح، نرخها در [0,1] | همه پاس |

اجرا: `python -m pytest tests/ai -q`.

### چکلیست دستی مرورگر (گام طلایی — بعد از بالا آمدن بکاند)

- [ ] بیمارستان: انتخاب H07 + ثبت ۲ واحد O+ red_cells urgent → کارت درخواست ظاهر میشود؛ جزئیات شمارندهها را نشان میدهد.
- [ ] خطا: توکن غلط → toast «توکن نامعتبر»؛ hospital_id=H98 → «بیمارستان ثبتنشده».
- [ ] مرکز: با توکن coordinator درخواست pending_review (در صورت وجود) تأیید میشود؛ جدول موجودی زنده است.
- [ ] اهداکننده: D00001 دعوتش را میبیند → میپذیرد → arrived → donated → در نمای بیمارستان fulfilled افزایش مییابد.
- [ ] amend روی درخواست لغوشده → toast وضعیت مجاز نیست (409).
- [ ] polling بدون خطای کنسول حداقل ۲ دقیقه.

### ارزیابی مدل (خروجی عددی واقعی، نه ادعا)

- `python scripts/train_model.py` موفق؛ `python scripts/evaluate_model.py` دو عدد چاپ میکند (AUC و مقایسه پیام/پذیرش) — این اعداد را در `docs/ai_module.md` ثبت کن.

---

## ح) معیارهای اتمام کار (چکلیست)

- [ ] همه فایلهای بخش «د» ساخته شدهاند؛ هیچ فایلی خارج از مالکیت تو تغییر نکرده است.
- [ ] هر سه نما با سرویس واقعی در مرورگر تست شدهاند (چکلیست بالا کامل تیک خورده).
- [ ] هیچ وابستگی خارجی/CDN در static نیست؛ صفحات RTL و responsive هستند.
- [ ] همه نام فیلدها/enumها/مسیرها دقیقاً مطابق CONTRACT بخش ۹ است (هیچ نام ابداعی).
- [ ] مدل آموزش دیده، آرتیفکت commit شده، `tests/ai` سبز، و خروجی `evaluate_model.py` در `docs/ai_module.md` ثبت است.
- [ ] استراتژی در حالت `ai_response` و `travel_time` هر دو بدون خطا کار میکنند (fallback تست شده).
- [ ] `docs/ai_module.md` (ورودی/خروجی/ارزیابی/محدودیتها) کامل و تحویل DEV-02 برای DECLARED شده است.
- [ ] اگر ماژول AI کامل نشد: **هیچ ادعایی در DECLARED نمیشود** و `RANKING_STRATEGY` روی `travel_time` میماند (تصمیم صادقانه تیم).
- [ ] PRها merge شده و master سالم است.
- [ ] موانع واقعی (مثلاً نبود بکاند در زمان تست) صادقانه گزارش شدهاند.

---

## نکات عملیاتی نهایی برای عامل برنامهنویس

- بکاند (DEV-01) موازی با تو ساخته میشود؛ قرارداد بخش «هـ» **قفل شده** است — با اطمینان روی همان کدنویسی کن و mock را commit نکن.
- مدل را فقط بعد از سالم بودن سه نما شروع کن (ریسک اعلام قابلیت ناقص = جریمه).
- فایلهای `app/domain/ranking.py` و `app/main.py` ممکن است هنگام کار تو هنوز نباشند — import ها را طوری بنویس که فقط داخل توابع/سازنده انجام شوند و در نبودشان اسکریپتهای train/evaluate مستقل بمانند.
- آرتیفکت مدل را حتماً commit کن (دموی داوران بدون آموزش مجدد باید کار کند).
- پیام commit انگلیسی؛ قبل از commit فقط فایلهای خودت را add کن.
- اگر تستی اجرا نشده، ادعای اجرا نکن؛ خروجیها را ضمیمه گزارش کن.

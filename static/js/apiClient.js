// BloodNet — shared frontend infrastructure (T1)
// Relative fetch, token handling, error mapping, polling and formatting helpers.

export const TOKEN_KEYS = {
  hospital: 'bloodnet_hospital_token',
  coordinator: 'bloodnet_coordinator_token',
};

export const ERROR_MESSAGES = {
  unauthorized: 'توکن نامعتبر است. لطفاً توکن را بررسی و دوباره ذخیره کنید.',
  not_found: 'درخواست موردنظر یافت نشد.',
  missing_idempotency_key: 'کلید یکتایی (Idempotency-Key) ارسال نشده است.',
  idempotency_key_reuse: 'کلید یکتای تکراری با بدنه متفاوت ارسال شده است.',
  validation_error: 'مقادیر واردشده نامعتبر است.',
  unknown_hospital: 'بیمارستان ثبت‌نشده است.',
  not_amendable: 'وضعیت فعلی درخواست اجازه اصلاح نمی‌دهد.',
  not_approvable: 'این درخواست در وضعیت قابل تأیید نیست.',
  internal_error: 'خطای داخلی سرویس رخ داده است.',
  network: 'اتصال به سرویس برقرار نشد.',
};

export const STATUS_FA = {
  pending_review: 'در انتظار تأیید',
  open: 'باز',
  mobilizing: 'در حال بسیج',
  partially_fulfilled: 'تأمین ناقص',
  fulfilled: 'تأمین کامل',
  cancelled: 'لغو شده',
  expired: 'منقضی شده',
};

export const PRODUCT_FA = {
  red_cells: 'گلبول قرمز',
  platelets: 'پلاکت',
  plasma: 'پلاسما',
};

export const URGENCY_FA = {
  critical: 'بحرانی',
  urgent: 'فوری',
  planned: 'برنامه‌ریزی‌شده',
};

const fa = (n) => Number(n).toLocaleString('fa-IR', { maximumFractionDigits: 1 });

/**
 * JSON fetch wrapper with token injection and Persian error mapping.
 * @param {string} method  HTTP method
 * @param {string} path    relative path (same origin, no CORS)
 * @param {object} opts    { tokenKey?, body? }
 * @returns {Promise<any>}
 */
export async function apiRequest(method, path, { tokenKey = null, body = null, headers: extraHeaders = null } = {}) {
  const headers = { 'Content-Type': 'application/json', ...(extraHeaders || {}) };
  if (tokenKey) {
    const token = localStorage.getItem(tokenKey) || '';
    headers.Authorization = `Bearer ${token}`;
  }
  let res;
  try {
    res = await fetch(path, {
      method,
      headers,
      body: body === null ? undefined : JSON.stringify(body),
    });
  } catch {
    throw { status: 0, code: 'network', message: ERROR_MESSAGES.network };
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const code = data?.error?.code || 'internal_error';
    const message = ERROR_MESSAGES[code] || data?.error?.message || 'خطای ناشناخته';
    throw { status: res.status, code, message };
  }
  return data;
}

export function getClock() {
  return apiRequest('GET', '/api/clock');
}

/**
 * Polling helper: runs fn immediately, then every intervalMs.
 * Overlapping runs are skipped. Returns a stop function.
 */
export function poll(fn, intervalMs) {
  let running = false;
  let timer = null;
  const tick = async () => {
    if (running) return;
    running = true;
    try {
      await fn();
    } finally {
      running = false;
    }
  };
  tick();
  timer = setInterval(tick, intervalMs);
  return () => clearInterval(timer);
}

/** "روز ۱ · ۰۵:۱۲" — short simulation clock format for the header chip. */
export function formatSimClock(min) {
  if (min === null || min === undefined || Number.isNaN(min)) return '—';
  const days = Math.floor(min / 1440);
  const h = Math.floor((min % 1440) / 60);
  const m = Math.floor(min % 60);
  const hh = String(h).padStart(2, '0');
  const mm = String(m).padStart(2, '0');
  return `روز ${fa(days)} · ${fa(hh)}:${fa(mm)}`;
}

/** "۲ ساعت و ۱۵ دقیقه" — human duration for countdowns and ages. */
export function formatSimDuration(min) {
  if (min === null || min === undefined || Number.isNaN(min)) return '—';
  if (min < 1) return 'کمتر از یک دقیقه';
  const days = Math.floor(min / 1440);
  const h = Math.floor((min % 1440) / 60);
  const m = Math.round(min % 60);
  const parts = [];
  if (days > 0) parts.push(`${fa(days)} روز`);
  if (h > 0) parts.push(`${fa(h)} ساعت`);
  if (m > 0) parts.push(`${fa(m)} دقیقه`);
  return parts.join(' و ');
}

/** Remaining SLA as text + severity, from a RequestDetail snapshot. */
export function slaInfo(detail) {
  const remaining = detail.sla_deadline_sim_min - detail.sim_min;
  if (remaining <= 0) return { text: 'مهلت گذشته است', cls: 'sla-chip--late', remaining };
  const warn = remaining < detail.sla_deadline_sim_min - detail.created_sim_min ? remaining < 60 : false;
  if (remaining < 60) return { text: `${formatSimDuration(remaining)} مانده`, cls: 'sla-chip--warn', remaining };
  return { text: `${formatSimDuration(remaining)} مانده`, cls: 'sla-chip--ok', remaining };
}

/**
 * Toast notification (success | error | info).
 * Aria-live container announces messages for screen readers.
 */
export function toast(message, type = 'info') {
  let box = document.getElementById('toasts');
  if (!box) {
    box = document.createElement('div');
    box.id = 'toasts';
    box.setAttribute('aria-live', 'polite');
    document.body.appendChild(box);
  }
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  const icons = {
    success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12l5 5L20 7"/></svg>',
    error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l10 18H2L12 3z"/><path d="M12 10v4"/><path d="M12 17.5h.01"/></svg>',
    info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M12 11v5"/></svg>',
  };
  el.innerHTML = `${icons[type] || icons.info}<span>${escapeHtml(message)}</span>`;
  const close = document.createElement('button');
  close.setAttribute('aria-label', 'بستن');
  close.textContent = '×';
  close.addEventListener('click', () => el.remove());
  el.appendChild(close);
  box.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

export function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value ?? '';
  return div.innerHTML;
}

/* --------------------------------------------------------------------------
   Minimal inline icon set (no external icon libraries — offline constraint)
   -------------------------------------------------------------------------- */
const PATHS = {
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  drop: '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
  heart: '<path d="M20.8 5.6a5.3 5.3 0 0 0-7.5 0L12 6.9l-1.3-1.3a5.3 5.3 0 0 0-7.5 7.5L12 21l8.8-8.9a5.3 5.3 0 0 0 0-7.5z"/>',
  box: '<path d="M21 8l-9-5-9 5v8l9 5 9-5V8z"/><path d="M3 8l9 5 9-5"/><path d="M12 13v8"/>',
  check: '<path d="M4 12l5 5L20 7"/>',
  x: '<path d="M6 6l12 12"/><path d="M18 6L6 18"/>',
  alert: '<path d="M12 3l10 18H2L12 3z"/><path d="M12 10v4"/><path d="M12 17.5h.01"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  building: '<path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16"/><path d="M2 21h20"/><path d="M9 7h2"/><path d="M9 11h2"/><path d="M9 15h2"/><path d="M13 7h2"/><path d="M13 11h2"/><path d="M13 15h2"/>',
  truck: '<path d="M1 8h13v8H1z"/><path d="M14 11h4l4 3v2h-8"/><circle cx="6" cy="18.5" r="1.8"/><circle cx="17" cy="18.5" r="1.8"/>',
  send: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/>',
  layers: '<path d="M12 2l10 5-10 5L2 7l10-5z"/><path d="M2 12l10 5 10-5"/><path d="M2 17l10 5 10-5"/>',
};

export function icon(name, size = 18) {
  const body = PATHS[name] || PATHS.drop;
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

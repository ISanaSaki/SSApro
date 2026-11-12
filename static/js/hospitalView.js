// BloodNet — Hospital view (T2)
// Token + hospital selection, request creation, live list/detail with polling.

import {
  apiRequest, getClock, poll, formatSimClock, formatSimDuration, slaInfo,
  toast, escapeHtml, icon, TOKEN_KEYS, STATUS_FA, PRODUCT_FA, URGENCY_FA,
} from './apiClient.js';

const TOKEN_KEY = TOKEN_KEYS.hospital;
const HOSPITAL_KEY = 'bloodnet_hospital_id';

const state = {
  token: localStorage.getItem(TOKEN_KEY) || '',
  hospitalId: localStorage.getItem(HOSPITAL_KEY) || '',
  hospitals: [],
  requests: [],
  detailId: null,
  detail: null,
  clock: null,
  stopList: null,
  stopDetail: null,
};

const $ = (id) => document.getElementById(id);
const els = {
  clockValue: $('clockValue'),
  clockChip: $('clockChip'),
  tokenInput: $('tokenInput'),
  tokenSave: $('tokenSave'),
  hospitalSelect: $('hospitalSelect'),
  statActive: $('statActive'),
  statPending: $('statPending'),
  statFulfilled: $('statFulfilled'),
  statShortage: $('statShortage'),
  requestForm: $('requestForm'),
  fProduct: $('fProduct'),
  fBloodGroup: $('fBloodGroup'),
  fUnits: $('fUnits'),
  fUrgency: $('fUrgency'),
  fNote: $('fNote'),
  noteCounter: $('noteCounter'),
  submitBtn: $('submitBtn'),
  newRequestBtn: $('newRequestBtn'),
  listCount: $('listCount'),
  lastUpdated: $('lastUpdated'),
  requestGrid: $('requestGrid'),
  emptyState: $('emptyState'),
  formSection: $('formSection'),
  listSection: $('listSection'),
  detailSection: $('detailSection'),
  detailBody: $('detailBody'),
  backBtn: $('backBtn'),
  amendModal: $('amendModal'),
  amendSub: $('amendSub'),
  amendChoices: $('amendChoices'),
  amendConfirm: $('amendConfirm'),
  amendClose: $('amendClose'),
  cancelModal: $('cancelModal'),
  cancelReqId: $('cancelReqId'),
  cancelConfirm: $('cancelConfirm'),
  cancelClose: $('cancelClose'),
};

const fa = (n) => Number(n).toLocaleString('fa-IR', { maximumFractionDigits: 1 });
const ACTIVE_STATUSES = ['open', 'mobilizing', 'partially_fulfilled'];
const TERMINAL_STATUSES = ['fulfilled', 'cancelled', 'expired'];

/* --------------------------------------------------------------------------
   Clock
   -------------------------------------------------------------------------- */
async function refreshClock() {
  try {
    state.clock = await getClock();
    els.clockValue.textContent = formatSimClock(state.clock.sim_time);
    els.clockChip.title = `سرعت شبیه‌سازی ×${state.clock.speed}`;
  } catch {
    els.clockValue.textContent = '—';
  }
}

/* --------------------------------------------------------------------------
   Hospitals
   -------------------------------------------------------------------------- */
async function loadHospitals() {
  try {
    const data = await apiRequest('GET', '/api/hospitals', { tokenKey: TOKEN_KEY });
    state.hospitals = data.hospitals || [];
  } catch (e) {
    toast(e.message, 'error');
    state.hospitals = [];
  }
  const current = state.hospitalId;
  els.hospitalSelect.innerHTML = '<option value="">انتخاب بیمارستان…</option>'
    + state.hospitals.map((h) => `<option value="${escapeHtml(h.hospital_id)}">${escapeHtml(h.hospital_id)} — ${escapeHtml(h.name)}</option>`).join('');
  if (current && state.hospitals.some((h) => h.hospital_id === current)) {
    els.hospitalSelect.value = current;
  } else if (state.hospitals.length > 0) {
    state.hospitalId = state.hospitals[0].hospital_id;
    els.hospitalSelect.value = state.hospitalId;
    localStorage.setItem(HOSPITAL_KEY, state.hospitalId);
  }
  startListPolling();
}

/* --------------------------------------------------------------------------
   Request list + stats
   -------------------------------------------------------------------------- */
function startListPolling() {
  if (state.stopList) state.stopList();
  if (!state.hospitalId) {
    els.requestGrid.innerHTML = '';
    els.emptyState.hidden = true;
    els.listCount.textContent = '۰';
    renderStats();
    return;
  }
  state.stopList = poll(loadRequests, 5000);
}

async function loadRequests() {
  try {
    const data = await apiRequest('GET', `/api/requests?hospital_id=${encodeURIComponent(state.hospitalId)}`, { tokenKey: TOKEN_KEY });
    state.requests = data.requests || [];
    renderList();
    renderStats();
    const now = new Date();
    els.lastUpdated.textContent = `آخرین به‌روزرسانی: ${now.toLocaleTimeString('fa-IR')}`;
  } catch (e) {
    els.lastUpdated.textContent = 'خطا در دریافت فهرست';
    if (e.status === 401) focusToken();
    else toast(e.message, 'error');
  }
}

function renderStats() {
  const rs = state.requests;
  const active = rs.filter((r) => ACTIVE_STATUSES.includes(r.status)).length;
  const pending = rs.filter((r) => r.status === 'pending_review').length;
  const fulfilled = rs.filter((r) => r.status === 'fulfilled').length;
  const shortage = rs.reduce((sum, r) => sum + Math.max(0, r.shortage || 0), 0);
  els.statActive.textContent = fa(active);
  els.statPending.textContent = fa(pending);
  els.statFulfilled.textContent = fa(fulfilled);
  els.statShortage.textContent = fa(shortage);
}

function renderList() {
  els.listCount.textContent = fa(state.requests.length);
  if (state.requests.length === 0) {
    els.requestGrid.innerHTML = '';
    els.emptyState.hidden = false;
    return;
  }
  els.emptyState.hidden = true;
  els.requestGrid.innerHTML = state.requests.map(cardHtml).join('');
}

function progressBarHtml(r) {
  const total = Math.max(r.needed, 1);
  const fulfilled = Math.max(0, r.fulfilled || 0);
  const inflight = Math.max(0, r.stock_inflight || 0);
  const shortage = Math.max(0, r.needed - fulfilled - inflight);
  const segs = [];
  if (fulfilled > 0) segs.push(`<span class="seg seg--fulfilled" style="width:${(fulfilled / total) * 100}%"></span>`);
  if (inflight > 0) segs.push(`<span class="seg seg--inflight" style="width:${(inflight / total) * 100}%"></span>`);
  if (shortage > 0) segs.push(`<span class="seg seg--shortage" style="width:${(shortage / total) * 100}%"></span>`);
  return segs.join('');
}

function cardHtml(r) {
  const pct = r.needed > 0 ? Math.min(100, Math.round((r.fulfilled / r.needed) * 100)) : 0;
  const active = ACTIVE_STATUSES.includes(r.status);
  const sla = active ? slaInfo(r) : null;
  const chips = [
    `<span class="chip">${escapeHtml(PRODUCT_FA[r.product] || r.product)}</span>`,
    `<span class="chip">${escapeHtml(r.blood_group)}</span>`,
    `<span class="chip">${fa(r.units)} واحد</span>`,
    `<span class="chip chip--${escapeHtml(r.urgency)}">${escapeHtml(URGENCY_FA[r.urgency] || r.urgency)}</span>`,
  ].join('');
  return `
    <article class="card req-card" data-id="${escapeHtml(r.request_id)}" tabindex="0" role="button" aria-label="جزئیات درخواست ${escapeHtml(r.request_id)}">
      <div class="req-top">
        <span class="req-id">${escapeHtml(r.request_id)}</span>
        <span class="badge badge--${escapeHtml(r.status)}">${escapeHtml(STATUS_FA[r.status] || r.status)}</span>
      </div>
      <div class="req-chips">${chips}</div>
      <div class="req-progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">${progressBarHtml(r)}</div>
      <div class="req-meta-row">
        <span class="progress-label">تأمین: ${fa(r.fulfilled)} از ${fa(r.needed)} واحد (${fa(pct)}٪)</span>
        ${r.stock_inflight > 0 ? `<span class="chip">در راه از موجودی: ${fa(r.stock_inflight)}</span>` : ''}
      </div>
      <div class="req-meta-row">
        ${r.shortage > 0 && !TERMINAL_STATUSES.includes(r.status) ? `<span class="shortage-line">${icon('alert', 14)} کسری: ${fa(r.shortage)} واحد</span>` : '<span></span>'}
        ${sla ? `<span class="sla-chip ${sla.cls}">${icon('clock', 13)} ${escapeHtml(sla.text)}</span>` : ''}
      </div>
    </article>`;
}

/* --------------------------------------------------------------------------
   Detail
   -------------------------------------------------------------------------- */
async function openDetail(requestId) {
  state.detailId = requestId;
  els.detailSection.hidden = false;
  els.detailSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  if (state.stopDetail) state.stopDetail();
  state.stopDetail = poll(loadDetail, 3000);
}

function closeDetail() {
  state.detailId = null;
  state.detail = null;
  els.detailSection.hidden = true;
  if (state.stopDetail) { state.stopDetail(); state.stopDetail = null; }
  window.scrollTo({ top: els.listSection?.offsetTop || 0, behavior: 'smooth' });
}

async function loadDetail() {
  if (!state.detailId) return;
  try {
    const data = await apiRequest('GET', `/api/requests/${encodeURIComponent(state.detailId)}`, { tokenKey: TOKEN_KEY });
    state.detail = data;
    renderDetail();
  } catch (e) {
    if (e.status === 404) { toast(e.message, 'error'); closeDetail(); }
    else if (e.status === 401) focusToken();
    else toast(e.message, 'error');
  }
}

function renderDetail() {
  const d = state.detail;
  if (!d) return;
  const active = ACTIVE_STATUSES.includes(d.status);
  const terminal = TERMINAL_STATUSES.includes(d.status);
  const pct = d.needed > 0 ? Math.min(100, Math.round((d.fulfilled / d.needed) * 100)) : 0;
  const counters = [
    { label: 'نیاز', value: d.needed },
    { label: 'تأیید شده', value: d.confirmed },
    { label: 'در مسیر', value: d.en_route },
    { label: 'حاضر در مرکز', value: d.arrived },
    { label: 'تأمین شده', value: d.fulfilled },
    { label: 'در راه (موجودی)', value: d.stock_inflight },
    ...(terminal ? [] : [{ label: 'کسری', value: d.shortage, alert: d.shortage > 0 }]),
  ];
  els.detailBody.innerHTML = `
    <div class="detail-head">
      <span class="req-id">${escapeHtml(d.request_id)}</span>
      <span class="badge badge--${escapeHtml(d.status)}">${escapeHtml(STATUS_FA[d.status] || d.status)}</span>
      ${active ? `<span class="sla-chip ${slaInfo(d).cls}">${icon('clock', 13)} ${escapeHtml(slaInfo(d).text)}</span>` : ''}
    </div>
    <div class="detail-meta">
      <span class="chip">${escapeHtml(PRODUCT_FA[d.product] || d.product)}</span>
      <span class="chip">${escapeHtml(d.blood_group)}</span>
      <span class="chip">${fa(d.units)} واحد</span>
      <span class="chip chip--${escapeHtml(d.urgency)}">${escapeHtml(URGENCY_FA[d.urgency] || d.urgency)}</span>
      <span class="chip">ثبت: ${escapeHtml(formatSimClock(d.created_sim_min))}</span>
      ${d.note ? `<span class="chip">یادداشت دارد</span>` : ''}
    </div>
    <div class="req-progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">${progressBarHtml(d)}</div>
    <div class="req-progress-legend" style="margin-top:6px">
      <span class="lg"><span class="swatch" style="background:#3e7a5f"></span>تأمین‌شده</span>
      <span class="lg"><span class="swatch" style="background:#7fb5c9"></span>در راه از موجودی</span>
      <span class="lg"><span class="swatch" style="background:#e05555"></span>کسری</span>
    </div>
    <div class="req-meta-row">
      <span class="progress-label">پیشرفت تأمین: ${fa(d.fulfilled)} از ${fa(d.needed)} واحد (${fa(pct)}٪)</span>
      <span class="hint">آخرین به‌روزرسانی وضعیت: ${escapeHtml(formatSimClock(d.updated_sim_min))}</span>
    </div>
    ${d.note ? `<div class="warn-note" style="margin-top:12px">${icon('alert', 16)}<span>یادداشت درخواست: ${escapeHtml(d.note)}</span></div>` : ''}
    <div class="counter-grid">
      ${counters.map((c) => `
        <div class="counter-tile ${c.alert ? 'counter-tile--alert' : ''}">
          <div class="counter-value">${fa(c.value)}</div>
          <div class="counter-label">${escapeHtml(c.label)}</div>
        </div>`).join('')}
    </div>
    <div class="detail-columns">
      <div class="card" style="box-shadow:none">
        <h3 class="card-title">${icon('clock', 16)} خط زمانی رویدادها</h3>
        ${timelineHtml(d.events || [])}
      </div>
      <div class="card" style="box-shadow:none">
        <h3 class="card-title">${icon('box', 16)} تخصیص‌های موجودی</h3>
        ${dispatchesHtml(d.dispatches || [])}
      </div>
    </div>
    <div class="detail-actions">
      <button class="btn btn-outline btn-sm" id="amendBtn" type="button" ${active ? '' : 'disabled'}>اصلاح فوریت</button>
      <button class="btn btn-danger btn-sm" id="cancelBtn" type="button" ${terminal ? 'disabled' : ''}>لغو درخواست</button>
      <span class="hint">${terminal ? 'این درخواست به وضعیت پایانی رسیده است.' : ''}</span>
    </div>`;
  const amendBtn = $('amendBtn');
  const cancelBtn = $('cancelBtn');
  if (amendBtn && active) amendBtn.addEventListener('click', openAmendModal);
  if (cancelBtn && !terminal) cancelBtn.addEventListener('click', openCancelModal);
}

const EVENT_TITLE = {
  donor_response_accepted: 'پذیرش دعوت',
  donor_response_declined: 'رد دعوت',
  progress_en_route: 'در مسیر مراجعه به مرکز',
  progress_arrived: 'حضور در مرکز',
  progress_screen_pass: 'تأیید غربالگری',
  progress_screen_fail: 'رد در غربالگری',
  progress_donated: 'اهدای موفق',
  progress_no_show: 'عدم مراجعه',
  gateway_queued: 'اعلان در صف ارسال',
  gateway_sent: 'اعلان ارسال شد',
  gateway_delivered: 'اعلان تحویل شد',
  gateway_failed: 'ارسال اعلان ناموفق',
  gateway_expired: 'اعلان منقضی شد',
  stock_delivery: 'تحویل واحد موجودی',
};

function eventKey(ev) {
  if (ev.kind === 'donor_response') return `donor_response_${ev.response}`;
  if (ev.kind === 'donor_progress') return `progress_${ev.event}`;
  if (ev.kind === 'gateway_status') return `gateway_${ev.status}`;
  return 'stock_delivery';
}

function eventDotClass(ev) {
  const map = {
    donor_response_accepted: 'ev-dot--accepted',
    donor_response_declined: 'ev-dot--declined',
    progress_en_route: 'ev-dot--en_route',
    progress_arrived: 'ev-dot--arrived',
    progress_screen_pass: 'ev-dot--screen_pass',
    progress_screen_fail: 'ev-dot--screen_fail',
    progress_donated: 'ev-dot--donated',
    progress_no_show: 'ev-dot--no_show',
    gateway_queued: 'ev-dot--queued',
    gateway_sent: 'ev-dot--sent',
    gateway_delivered: 'ev-dot--delivered',
    gateway_failed: 'ev-dot--failed',
    gateway_expired: 'ev-dot--expired',
    stock_delivery: 'ev-dot--delivered',
  };
  return map[eventKey(ev)] || 'ev-dot--queued';
}

function timelineHtml(events) {
  if (!events.length) return '<p class="hint">هنوز رویدادی ثبت نشده است.</p>';
  const sorted = [...events].sort((a, b) => b.sim_time - a.sim_time);
  return `<ul class="timeline">${sorted.map((ev) => `
    <li>
      <span class="ev-dot ${eventDotClass(ev)}"></span>
      <span class="ev-body">
        <span class="ev-title">${escapeHtml(EVENT_TITLE[eventKey(ev)] || ev.event || ev.status || 'رویداد')}</span>
        <br><span class="ev-sub">${ev.donor_id ? `اهداکننده ${escapeHtml(ev.donor_id)}` : ''}${ev.reason ? ` — ${escapeHtml(ev.reason)}` : ''}</span>
      </span>
      <span class="ev-time">${escapeHtml(formatSimClock(ev.sim_time))}</span>
    </li>`).join('')}</ul>`;
}

const OUTCOME_FA = { created: 'در حال تحویل', delivered: 'تحویل شده', failed: 'ناموفق' };
const OUTCOME_CLS = { created: 'badge--open', delivered: 'badge--fulfilled', failed: 'badge--expired' };

function dispatchesHtml(dispatches) {
  if (!dispatches.length) return '<p class="hint">تخصیص موجودی برای این درخواست ثبت نشده است.</p>';
  return `
    <div class="table-wrap">
      <table>
        <thead><tr><th>مرکز</th><th>گروه</th><th>محصول</th><th>واحد</th><th>زمان تحویل</th><th>وضعیت</th></tr></thead>
        <tbody>
          ${dispatches.map((dp) => `
            <tr>
              <td>${escapeHtml(dp.center_id)}</td>
              <td>${escapeHtml(dp.blood_group)}</td>
              <td>${escapeHtml(PRODUCT_FA[dp.product] || dp.product)}</td>
              <td>${fa(dp.units)}</td>
              <td>${escapeHtml(formatSimClock(dp.delivery_sim_min))}</td>
              <td><span class="badge ${OUTCOME_CLS[dp.outcome] || 'badge--open'}">${escapeHtml(OUTCOME_FA[dp.outcome] || dp.outcome)}</span></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

/* --------------------------------------------------------------------------
   Amend / cancel modals
   -------------------------------------------------------------------------- */
function openAmendModal() {
  const d = state.detail;
  if (!d) return;
  els.amendSub.textContent = `درخواست ${d.request_id} — فوریت فعلی: ${URGENCY_FA[d.urgency] || d.urgency}`;
  const radio = els.amendChoices.querySelector(`input[value="${d.urgency}"]`);
  els.amendChoices.querySelectorAll('label.choice').forEach((l) => {
    l.classList.toggle('selected', l.dataset.value === d.urgency);
  });
  if (radio) radio.checked = true;
  els.amendModal.classList.add('open');
}

function openCancelModal() {
  const d = state.detail;
  if (!d) return;
  els.cancelReqId.textContent = d.request_id;
  els.cancelModal.classList.add('open');
}

function closeModals() {
  els.amendModal.classList.remove('open');
  els.cancelModal.classList.remove('open');
}

async function submitAmend() {
  const choice = els.amendChoices.querySelector('input[name="amendUrgency"]:checked');
  if (!choice) return toast('یک سطح فوریت انتخاب کنید.', 'error');
  try {
    await apiRequest('POST', `/requests/${encodeURIComponent(state.detailId)}/amend`, {
      tokenKey: TOKEN_KEY, body: { urgency: choice.value },
    });
    toast('سطح فوریت به‌روزرسانی شد.', 'success');
    closeModals();
    loadDetail();
    loadRequests();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function submitCancel() {
  try {
    await apiRequest('POST', `/requests/${encodeURIComponent(state.detailId)}/cancel`, { tokenKey: TOKEN_KEY, body: {} });
    toast('درخواست لغو شد.', 'success');
    closeModals();
    loadDetail();
    loadRequests();
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* --------------------------------------------------------------------------
   Create request
   -------------------------------------------------------------------------- */
function validateForm() {
  let ok = true;
  const fields = [els.fUnits];
  const units = Number(els.fUnits.value);
  if (!Number.isInteger(units) || units < 1 || units > 20) {
    els.fUnits.classList.add('invalid');
    ok = false;
  } else {
    els.fUnits.classList.remove('invalid');
  }
  fields.forEach((f) => f.classList.remove('invalid'));
  if (!ok) toast('تعداد واحد باید عددی بین ۱ تا ۲۰ باشد.', 'error');
  return ok;
}

async function submitForm(e) {
  e.preventDefault();
  if (!state.hospitalId) return toast('ابتدا بیمارستان خود را انتخاب کنید.', 'error');
  if (!localStorage.getItem(TOKEN_KEY)) { focusToken(); return toast('ابتدا توکن بیمارستان را وارد و ذخیره کنید.', 'error'); }
  if (!validateForm()) return;
  const body = {
    hospital_id: state.hospitalId,
    blood_group: els.fBloodGroup.value,
    product: els.fProduct.value,
    units: Number(els.fUnits.value),
    urgency: els.fUrgency.value,
  };
  const note = els.fNote.value.trim();
  if (note) body.note = note;
  els.submitBtn.disabled = true;
  els.submitBtn.innerHTML = '<span class="spinner"></span> در حال ارسال…';
  try {
    const created = await apiRequest('POST', '/requests', {
      tokenKey: TOKEN_KEY,
      body,
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    toast(`درخواست ${created.request_id} با موفقیت ثبت شد.`, 'success');
    els.requestForm.reset();
    els.fUnits.value = '2';
    els.noteCounter.textContent = '۰ / ۵۰۰';
    loadRequests();
    if (created.request_id) openDetail(created.request_id);
  } catch (err) {
    if (err.status === 401) focusToken();
    toast(err.message, 'error');
  } finally {
    els.submitBtn.disabled = false;
    els.submitBtn.innerHTML = `${icon('send', 16)} ارسال درخواست`;
  }
}

function focusToken() {
  els.tokenInput.focus();
  els.tokenInput.select();
}

/* --------------------------------------------------------------------------
   Init
   -------------------------------------------------------------------------- */
function init() {
  els.tokenInput.value = state.token;
  els.tokenSave.addEventListener('click', () => {
    state.token = els.tokenInput.value.trim();
    if (state.token) {
      localStorage.setItem(TOKEN_KEY, state.token);
      toast('توکن ذخیره شد.', 'success');
      loadHospitals();
      if (state.hospitalId) loadRequests();
    } else {
      localStorage.removeItem(TOKEN_KEY);
      toast('توکن حذف شد.', 'info');
    }
  });
  els.tokenInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') els.tokenSave.click(); });

  els.hospitalSelect.addEventListener('change', () => {
    state.hospitalId = els.hospitalSelect.value;
    if (state.hospitalId) localStorage.setItem(HOSPITAL_KEY, state.hospitalId);
    else localStorage.removeItem(HOSPITAL_KEY);
    startListPolling();
  });

  els.newRequestBtn.addEventListener('click', () => {
    els.formSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    els.fProduct.focus();
  });

  els.requestForm.addEventListener('submit', submitForm);
  els.fNote.addEventListener('input', () => {
    els.noteCounter.textContent = `${fa(els.fNote.value.length)} / ۵۰۰`;
  });

  els.requestGrid.addEventListener('click', (e) => {
    const card = e.target.closest('.req-card');
    if (card) openDetail(card.dataset.id);
  });
  els.requestGrid.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      const card = e.target.closest('.req-card');
      if (card) { e.preventDefault(); openDetail(card.dataset.id); }
    }
  });

  els.backBtn.addEventListener('click', closeDetail);

  els.amendChoices.querySelectorAll('label.choice').forEach((l) => {
    l.addEventListener('click', () => {
      els.amendChoices.querySelectorAll('label.choice').forEach((x) => x.classList.remove('selected'));
      l.classList.add('selected');
    });
  });
  els.amendConfirm.addEventListener('click', submitAmend);
  els.amendClose.addEventListener('click', closeModals);
  els.cancelConfirm.addEventListener('click', submitCancel);
  els.cancelClose.addEventListener('click', closeModals);
  els.amendModal.addEventListener('click', (e) => { if (e.target === els.amendModal) closeModals(); });
  els.cancelModal.addEventListener('click', (e) => { if (e.target === els.cancelModal) closeModals(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModals(); });

  refreshClock();
  poll(refreshClock, 5000);
  loadHospitals();
}

init();

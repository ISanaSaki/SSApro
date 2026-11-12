// BloodNet — Donor view (T4)
// Fetch invitations, respond accept/decline, drive the donation progress flow.

import {
  apiRequest, getClock, poll, formatSimClock,
  toast, escapeHtml, icon, STATUS_FA,
} from './apiClient.js';

const DONOR_KEY = 'bloodnet_donor_id';

const state = {
  donorId: localStorage.getItem(DONOR_KEY) || '',
  invitations: [],
  clock: null,
};

const $ = (id) => document.getElementById(id);
const els = {
  clockValue: $('clockValue'),
  donorId: $('donorId'),
  donorForm: $('donorForm'),
  fetchBtn: $('fetchBtn'),
  invGrid: $('invGrid'),
  invCount: $('invCount'),
  invUpdated: $('invUpdated'),
  emptyState: $('emptyState'),
};

const fa = (n) => Number(n).toLocaleString('fa-IR', { maximumFractionDigits: 1 });

const TEMPLATE_FA = {
  request_wave: 'موج دعوت',
  confirmed: 'تأیید نهایی',
  not_needed: 'نیاز برطرف شد',
  cancelled: 'لغو شده',
  reminder: 'یادآوری',
};

const GATEWAY_FA = {
  queued: 'در صف ارسال',
  sent: 'ارسال شده',
  delivered: 'تحویل شده',
  failed: 'ناموفق',
  expired: 'منقضی',
};

const RESPONSE_FA = { accepted: 'پذیرفته‌شده', declined: 'رد شده' };
const EVENT_FA = {
  en_route: 'در مسیر مرکز',
  arrived: 'حاضر در مرکز',
  screen_pass: 'تأیید غربالگری',
  screen_fail: 'رد در غربالگری',
  donated: 'اهدای موفق',
  no_show: 'عدم مراجعه',
};

const TERMINAL_EVENTS = ['donated', 'no_show', 'screen_fail'];
const TERMINAL_TEMPLATES = ['not_needed', 'cancelled'];

/* --------------------------------------------------------------------------
   Clock
   -------------------------------------------------------------------------- */
async function refreshClock() {
  try {
    state.clock = await getClock();
    els.clockValue.textContent = formatSimClock(state.clock.sim_time);
  } catch {
    els.clockValue.textContent = '—';
  }
}

/* --------------------------------------------------------------------------
   Invitations
   -------------------------------------------------------------------------- */
async function loadInvitations() {
  if (!state.donorId) return;
  try {
    const data = await apiRequest('GET', `/api/donor/invitations?donor_id=${encodeURIComponent(state.donorId)}`);
    state.invitations = data.invitations || [];
    renderInvitations();
    const now = new Date();
    els.invUpdated.textContent = `آخرین به‌روزرسانی: ${now.toLocaleTimeString('fa-IR')}`;
  } catch (e) {
    els.invUpdated.textContent = 'خطا در دریافت دعوت‌ها';
    toast(e.message, 'error');
  }
}

function invitationState(inv) {
  if (TERMINAL_TEMPLATES.includes(inv.template)) return { cls: 'badge--cancelled', text: TEMPLATE_FA[inv.template] || inv.template };
  if (inv.event) return { cls: eventBadge(inv.event), text: EVENT_FA[inv.event] || inv.event };
  if (inv.response === 'declined') return { cls: 'badge--expired', text: RESPONSE_FA.declined };
  if (inv.response === 'accepted') return { cls: 'badge--fulfilled', text: RESPONSE_FA.accepted };
  return { cls: 'badge--open', text: GATEWAY_FA[inv.gateway_status] || inv.gateway_status || 'در انتظار پاسخ' };
}

function eventBadge(event) {
  const map = {
    en_route: 'badge--mobilizing',
    arrived: 'badge--open',
    screen_pass: 'badge--fulfilled',
    screen_fail: 'badge--expired',
    donated: 'badge--fulfilled',
    no_show: 'badge--cancelled',
  };
  return map[event] || 'badge--open';
}

function actionsHtml(inv) {
  if (TERMINAL_TEMPLATES.includes(inv.template)) return '';
  if (inv.response === 'declined' || (inv.event && TERMINAL_EVENTS.includes(inv.event))) return '';
  if (!inv.response) {
    return `
      <div class="queue-actions">
        <button class="btn btn-primary btn-sm" data-action="respond" data-response="accepted" data-id="${escapeHtml(inv.request_id)}" type="button">${icon('check', 14)} می‌پذیرم</button>
        <button class="btn btn-danger btn-sm" data-action="respond" data-response="declined" data-id="${escapeHtml(inv.request_id)}" type="button">${icon('x', 14)} رد می‌کنم</button>
      </div>`;
  }
  if (inv.response === 'accepted' && !inv.event) {
    return `
      <div class="queue-actions">
        <button class="btn btn-primary btn-sm" data-action="progress" data-event="en_route" data-id="${escapeHtml(inv.request_id)}" type="button">${icon('truck', 14)} در مسیرم</button>
        <button class="btn btn-outline btn-sm" data-action="progress" data-event="no_show" data-id="${escapeHtml(inv.request_id)}" type="button">نمی‌رسم</button>
      </div>`;
  }
  if (inv.event === 'en_route') {
    return `
      <div class="queue-actions">
        <button class="btn btn-primary btn-sm" data-action="progress" data-event="arrived" data-id="${escapeHtml(inv.request_id)}" type="button">${icon('building', 14)} رسیدم</button>
        <button class="btn btn-outline btn-sm" data-action="progress" data-event="no_show" data-id="${escapeHtml(inv.request_id)}" type="button">نمی‌رسم</button>
      </div>`;
  }
  if (inv.event === 'arrived') {
    return `
      <div class="queue-actions">
        <button class="btn btn-primary btn-sm" data-action="progress" data-event="screen_pass" data-id="${escapeHtml(inv.request_id)}" type="button">${icon('check', 14)} غربالگری موفق</button>
        <button class="btn btn-danger btn-sm" data-action="progress" data-event="screen_fail" data-id="${escapeHtml(inv.request_id)}" type="button">رد غربالگری</button>
        <button class="btn btn-outline btn-sm" data-action="progress" data-event="no_show" data-id="${escapeHtml(inv.request_id)}" type="button">نمی‌رسم</button>
      </div>`;
  }
  if (inv.event === 'screen_pass') {
    return `
      <div class="queue-actions">
        <button class="btn btn-primary btn-sm" data-action="progress" data-event="donated" data-id="${escapeHtml(inv.request_id)}" type="button">${icon('heart', 14)} اهدا انجام شد</button>
        <button class="btn btn-outline btn-sm" data-action="progress" data-event="no_show" data-id="${escapeHtml(inv.request_id)}" type="button">نمی‌رسم</button>
      </div>`;
  }
  return '';
}

function renderInvitations() {
  const invs = state.invitations;
  els.invCount.textContent = fa(invs.length);
  if (invs.length === 0) {
    els.invGrid.innerHTML = '';
    els.emptyState.hidden = false;
    return;
  }
  els.emptyState.hidden = true;
  els.invGrid.innerHTML = invs.map((inv) => {
    const st = invitationState(inv);
    return `
      <article class="card req-card" data-id="${escapeHtml(inv.request_id)}">
        <div class="req-top">
          <span class="req-id">${escapeHtml(inv.request_id)}</span>
          <span class="badge ${st.cls}">${escapeHtml(st.text)}</span>
        </div>
        <div class="req-chips">
          <span class="chip">${escapeHtml(TEMPLATE_FA[inv.template] || inv.template)}</span>
          <span class="chip">${escapeHtml(inv.notification_id)}</span>
          <span class="chip">ارسال: ${escapeHtml(formatSimClock(inv.created_sim_min))}</span>
          ${inv.gateway_status && inv.gateway_status !== 'delivered' ? `<span class="chip">${escapeHtml(GATEWAY_FA[inv.gateway_status] || inv.gateway_status)}</span>` : ''}
        </div>
        ${inv.template === 'not_needed' || inv.template === 'cancelled' ? `
          <div class="req-meta-row"><span class="hint">این دعوت دیگر نیاز به اقدام ندارد؛ از مراجعه شما سپاسگزاریم.</span></div>` : ''}
        ${actionsHtml(inv)}
      </article>`;
  }).join('');
}

/* --------------------------------------------------------------------------
   Actions
   -------------------------------------------------------------------------- */
async function respond(requestId, response) {
  try {
    await apiRequest('POST', '/api/donor/respond', {
      body: { donor_id: state.donorId, request_id: requestId, response },
    });
    toast(response === 'accepted' ? 'دعوت پذیرفته شد. منتظر راهنمایی بعدی باشید.' : 'دعوت رد شد.', 'success');
    loadInvitations();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function progress(requestId, event) {
  try {
    await apiRequest('POST', '/api/donor/progress', {
      body: { donor_id: state.donorId, request_id: requestId, event },
    });
    toast(`رویداد «${EVENT_FA[event] || event}» ثبت شد.`, 'success');
    loadInvitations();
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* --------------------------------------------------------------------------
   Init
   -------------------------------------------------------------------------- */
function init() {
  els.donorId.value = state.donorId;

  els.donorForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const id = els.donorId.value.trim().toUpperCase();
    if (!id) return toast('شناسه اهداکننده را وارد کنید.', 'error');
    state.donorId = id;
    localStorage.setItem(DONOR_KEY, id);
    loadInvitations();
  });

  els.invGrid.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    if (btn.dataset.action === 'respond') respond(btn.dataset.id, btn.dataset.response);
    else progress(btn.dataset.id, btn.dataset.event);
  });

  refreshClock();
  poll(refreshClock, 5000);
  if (state.donorId) {
    loadInvitations();
    poll(loadInvitations, 5000);
  }
}

init();

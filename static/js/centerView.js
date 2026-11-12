// BloodNet — Center (coordinator) view (T3)
// Approve queue, network-wide request list with filter, live inventory, KPIs.

import {
  apiRequest, getClock, poll, formatSimClock, formatSimDuration,
  toast, escapeHtml, icon, TOKEN_KEYS, STATUS_FA, PRODUCT_FA, URGENCY_FA,
} from './apiClient.js';

const TOKEN_KEY = TOKEN_KEYS.coordinator;

// Frozen values from participant_kit/rules.yaml (shelf life in days).
const SHELF_DAYS = { red_cells: 42, platelets: 5, plasma: 365 };
const SHELF_WARN_PCT = 0.2;

const state = {
  requests: [],
  filter: '',
  inventory: { items: [], sim_time: null },
  clock: null,
};

const $ = (id) => document.getElementById(id);
const els = {
  clockValue: $('clockValue'),
  tokenInput: $('tokenInput'),
  tokenSave: $('tokenSave'),
  statActive: $('statActive'),
  statFulfilled: $('statFulfilled'),
  statShortage: $('statShortage'),
  statExpiring: $('statExpiring'),
  queueGrid: $('queueGrid'),
  queueCount: $('queueCount'),
  queueEmpty: $('queueEmpty'),
  requestGrid: $('requestGrid'),
  listCount: $('listCount'),
  emptyState: $('emptyState'),
  statusFilter: $('statusFilter'),
  invBody: $('invBody'),
  invCount: $('invCount'),
  invUpdated: $('invUpdated'),
  rejectModal: $('rejectModal'),
  rejectSub: $('rejectSub'),
  rejectNote: $('rejectNote'),
  rejectConfirm: $('rejectConfirm'),
  rejectClose: $('rejectClose'),
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
  } catch {
    els.clockValue.textContent = '—';
  }
}

/* --------------------------------------------------------------------------
   Requests (queue + list + stats)
   -------------------------------------------------------------------------- */
async function loadRequests() {
  try {
    const data = await apiRequest('GET', '/api/requests', { tokenKey: TOKEN_KEY });
    state.requests = data.requests || [];
    renderQueue();
    renderList();
    renderStats();
  } catch (e) {
    if (e.status === 401) { focusToken(); toast(e.message, 'error'); }
    else toast(e.message, 'error');
  }
}

function renderStats() {
  const rs = state.requests;
  const active = rs.filter((r) => ACTIVE_STATUSES.includes(r.status)).length;
  const fulfilled = rs.reduce((sum, r) => sum + (r.fulfilled || 0), 0);
  const shortage = rs.reduce((sum, r) => sum + (ACTIVE_STATUSES.includes(r.status) || r.status === 'pending_review' ? Math.max(0, r.shortage || 0) : 0), 0);
  const expiring = countExpiring();
  els.statActive.textContent = fa(active);
  els.statFulfilled.textContent = fa(fulfilled);
  els.statShortage.textContent = fa(shortage);
  els.statExpiring.textContent = fa(expiring);
}

function renderQueue() {
  const queue = state.requests.filter((r) => r.status === 'pending_review');
  els.queueCount.textContent = fa(queue.length);
  if (queue.length === 0) {
    els.queueGrid.innerHTML = '';
    els.queueEmpty.hidden = false;
    return;
  }
  els.queueEmpty.hidden = true;
  els.queueGrid.innerHTML = queue.map(queueCardHtml).join('');
}

function queueCardHtml(r) {
  return `
    <article class="card req-card queue-card" data-id="${escapeHtml(r.request_id)}">
      <div class="req-top">
        <span class="req-id">${escapeHtml(r.request_id)}</span>
        <span class="badge badge--pending_review">${escapeHtml(STATUS_FA.pending_review)}</span>
      </div>
      <div class="req-chips">
        <span class="chip">${escapeHtml(r.hospital_id)}</span>
        <span class="chip">${escapeHtml(PRODUCT_FA[r.product] || r.product)}</span>
        <span class="chip">${escapeHtml(r.blood_group)}</span>
        <span class="chip">${fa(r.units)} واحد</span>
        <span class="chip chip--${escapeHtml(r.urgency)}">${escapeHtml(URGENCY_FA[r.urgency] || r.urgency)}</span>
      </div>
      <div class="req-meta-row">
        <span class="hint">ثبت: ${escapeHtml(formatSimClock(r.created_sim_min))}</span>
        <span class="hint">${r.note ? `یادداشت: ${escapeHtml(r.note)}` : ''}</span>
      </div>
      <div class="queue-actions">
        <button class="btn btn-primary btn-sm" data-action="approve" data-id="${escapeHtml(r.request_id)}" type="button">${icon('check', 14)} تأیید</button>
        <button class="btn btn-danger btn-sm" data-action="reject" data-id="${escapeHtml(r.request_id)}" type="button">${icon('x', 14)} رد</button>
      </div>
    </article>`;
}

function renderList() {
  const filtered = state.filter
    ? state.requests.filter((r) => r.status === state.filter)
    : state.requests;
  els.listCount.textContent = fa(filtered.length);
  if (filtered.length === 0) {
    els.requestGrid.innerHTML = '';
    els.emptyState.hidden = false;
    return;
  }
  els.emptyState.hidden = true;
  els.requestGrid.innerHTML = filtered.map(listCardHtml).join('');
}

function listCardHtml(r) {
  const pct = r.needed > 0 ? Math.min(100, Math.round((r.fulfilled / r.needed) * 100)) : 0;
  const terminal = TERMINAL_STATUSES.includes(r.status);
  return `
    <article class="card req-card" data-id="${escapeHtml(r.request_id)}">
      <div class="req-top">
        <span class="req-id">${escapeHtml(r.request_id)}</span>
        <span class="badge badge--${escapeHtml(r.status)}">${escapeHtml(STATUS_FA[r.status] || r.status)}</span>
      </div>
      <div class="req-chips">
        <span class="chip">${escapeHtml(r.hospital_id)}</span>
        <span class="chip">${escapeHtml(PRODUCT_FA[r.product] || r.product)}</span>
        <span class="chip">${escapeHtml(r.blood_group)}</span>
        <span class="chip">${fa(r.units)} واحد</span>
        <span class="chip chip--${escapeHtml(r.urgency)}">${escapeHtml(URGENCY_FA[r.urgency] || r.urgency)}</span>
      </div>
      <div class="req-progress" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
        ${segmentsHtml(r)}
      </div>
      <div class="req-meta-row">
        <span class="progress-label">تأمین: ${fa(r.fulfilled)} از ${fa(r.needed)} واحد (${fa(pct)}٪)</span>
        ${r.stock_inflight > 0 ? `<span class="chip">در راه از موجودی: ${fa(r.stock_inflight)}</span>` : ''}
      </div>
      <div class="req-meta-row">
        ${r.shortage > 0 && !terminal ? `<span class="shortage-line">${icon('alert', 14)} کسری: ${fa(r.shortage)} واحد</span>` : '<span></span>'}
        <span class="hint">${escapeHtml(formatSimClock(r.created_sim_min))}</span>
      </div>
    </article>`;
}

function segmentsHtml(r) {
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

/* --------------------------------------------------------------------------
   Approve / reject
   -------------------------------------------------------------------------- */
async function approve(requestId) {
  try {
    await apiRequest('POST', `/requests/${encodeURIComponent(requestId)}/approve`, {
      tokenKey: TOKEN_KEY, body: { approved: true },
    });
    toast(`درخواست ${requestId} تأیید شد و چرخه تأمین آغاز شد.`, 'success');
    loadRequests();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function openRejectModal(requestId) {
  const r = state.requests.find((x) => x.request_id === requestId);
  els.rejectSub.textContent = `درخواست ${requestId}${r ? ` — ${fa(r.units)} واحد ${escapeHtml(r.blood_group)}` : ''}`;
  els.rejectNote.value = '';
  els.rejectModal.dataset.requestId = requestId;
  els.rejectModal.classList.add('open');
}

async function submitReject() {
  const requestId = els.rejectModal.dataset.requestId;
  const body = { approved: false };
  const note = els.rejectNote.value.trim();
  if (note) body.note = note;
  try {
    await apiRequest('POST', `/requests/${encodeURIComponent(requestId)}/approve`, { tokenKey: TOKEN_KEY, body });
    toast(`درخواست ${requestId} رد شد.`, 'success');
    closeRejectModal();
    loadRequests();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function closeRejectModal() {
  els.rejectModal.classList.remove('open');
}

/* --------------------------------------------------------------------------
   Inventory
   -------------------------------------------------------------------------- */
async function loadInventory() {
  try {
    const data = await apiRequest('GET', '/api/inventory', { tokenKey: TOKEN_KEY });
    state.inventory = data || { items: [] };
    renderInventory();
    renderStats();
    const now = new Date();
    els.invUpdated.textContent = `آخرین به‌روزرسانی: ${now.toLocaleTimeString('fa-IR')}`;
  } catch (e) {
    els.invUpdated.textContent = 'خطا در دریافت موجودی';
    if (e.status === 401) focusToken();
    else toast(e.message, 'error');
  }
}

function inventoryRowState(item, simTime) {
  const remaining = item.expires_sim_min - simTime;
  if (remaining <= 0) return { cls: 'badge--expired', text: 'منقضی' };
  const warnMin = (SHELF_DAYS[item.product] || 42) * 1440 * SHELF_WARN_PCT;
  if (remaining < warnMin) return { cls: 'badge--cancelled', text: 'رو به انقضا' };
  return { cls: 'badge--fulfilled', text: 'سالم' };
}

function countExpiring() {
  const simTime = state.inventory.sim_time ?? state.clock?.sim_time ?? 0;
  return state.inventory.items.filter((it) => {
    const remaining = it.expires_sim_min - simTime;
    const warnMin = (SHELF_DAYS[it.product] || 42) * 1440 * SHELF_WARN_PCT;
    return remaining > 0 && remaining < warnMin;
  }).length;
}

function renderInventory() {
  const items = state.inventory.items || [];
  const simTime = state.inventory.sim_time ?? state.clock?.sim_time ?? 0;
  els.invCount.textContent = fa(items.length);
  if (items.length === 0) {
    els.invBody.innerHTML = '<tr><td colspan="6" class="hint">موجودی ثبت نشده است.</td></tr>';
    return;
  }
  const sorted = [...items].sort((a, b) => a.expires_sim_min - b.expires_sim_min);
  els.invBody.innerHTML = sorted.map((it) => {
    const st = inventoryRowState(it, simTime);
    return `
      <tr>
        <td>${escapeHtml(it.center_id)}</td>
        <td>${escapeHtml(it.blood_group)}</td>
        <td>${escapeHtml(PRODUCT_FA[it.product] || it.product)}</td>
        <td>${fa(it.units)}</td>
        <td>${escapeHtml(formatSimClock(it.expires_sim_min))}</td>
        <td><span class="badge ${st.cls}">${escapeHtml(st.text)}</span></td>
      </tr>`;
  }).join('');
}

/* --------------------------------------------------------------------------
   Init
   -------------------------------------------------------------------------- */
function focusToken() {
  els.tokenInput.focus();
  els.tokenInput.select();
}

function init() {
  els.tokenInput.value = localStorage.getItem(TOKEN_KEY) || '';
  els.tokenSave.addEventListener('click', () => {
    const token = els.tokenInput.value.trim();
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      toast('توکن ذخیره شد.', 'success');
      loadRequests();
      loadInventory();
    } else {
      localStorage.removeItem(TOKEN_KEY);
      toast('توکن حذف شد.', 'info');
    }
  });
  els.tokenInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') els.tokenSave.click(); });

  els.statusFilter.addEventListener('change', () => {
    state.filter = els.statusFilter.value;
    renderList();
  });

  els.queueGrid.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    if (btn.dataset.action === 'approve') approve(btn.dataset.id);
    else openRejectModal(btn.dataset.id);
  });

  els.rejectConfirm.addEventListener('click', submitReject);
  els.rejectClose.addEventListener('click', closeRejectModal);
  els.rejectModal.addEventListener('click', (e) => { if (e.target === els.rejectModal) closeRejectModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeRejectModal(); });

  refreshClock();
  poll(refreshClock, 5000);
  loadRequests();
  poll(loadRequests, 5000);
  loadInventory();
  poll(loadInventory, 5000);
}

init();

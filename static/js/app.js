/* TaskNest front-end: shared helpers + one small module per page. Plain JavaScript, no frameworks. */

/* ============================== helpers ============================== */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pad = (n) => String(n).padStart(2, '0');
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const toLocalInput = (d) => `${ymd(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const fmtDue = (s) => new Date(s).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' });
const fmtTimeOnly = (s) => new Date(s).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const fmtInterval = (m) => (m % 60 === 0 ? `${m / 60}h` : `${m} min`);
const PAGE = document.body.dataset.page;
const TASKS = new Map();           // id -> latest task object (used by edit buttons)

async function api(path, opts = {}) {
  const o = { credentials: 'same-origin', headers: {}, ...opts };
  if (o.body && !(o.body instanceof FormData)) {
    o.headers['Content-Type'] = 'application/json';
    o.body = JSON.stringify(o.body);
  }
  const res = await fetch(path, o);
  let data = {};
  try { data = await res.json(); } catch (_) { /* empty body */ }
  if (res.status === 401) { location.href = '/login'; throw new Error('Please sign in.'); }
  if (!res.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
  return data;
}

function toast(message, type = 'info', ms = 4500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), ms);
}

function confetti() {
  const colors = ['#6c63ff', '#22b8a8', '#f5a300', '#ef476f', '#4cc9f0'];
  for (let i = 0; i < 46; i++) {
    const c = document.createElement('i');
    c.className = 'confetti';
    c.style.left = Math.random() * 100 + 'vw';
    c.style.background = colors[i % colors.length];
    c.style.animationDuration = 1.6 + Math.random() * 1.6 + 's';
    c.style.animationDelay = Math.random() * 0.3 + 's';
    c.style.transform = `rotate(${Math.random() * 360}deg)`;
    document.body.appendChild(c);
    setTimeout(() => c.remove(), 3800);
  }
}

/* ============================== modals =============================== */
function openModal(id) { $(id).hidden = false; }
function closeModals() { $$('.modal').forEach((m) => (m.hidden = true)); }
document.addEventListener('click', (e) => {
  if (e.target.matches('[data-close]') || e.target.classList.contains('modal')) closeModals();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModals(); });

/* ============================ task form ============================== */
let editingId = null;

function openTaskModal(task = null, defaults = {}) {
  const f = $('#taskForm');
  editingId = task ? task.id : null;
  $('#taskModalTitle').textContent = task ? 'Edit task' : 'New task';
  f.reset();
  $('#taskError').hidden = true;
  if (task) {
    f.title.value = task.title;
    f.description.value = task.description;
    f.category.value = task.category;
    f.priority.value = task.priority;
    f.due_datetime.value = task.due_datetime;
    f.reminder_interval_minutes.value = String(task.reminder_interval_minutes);
  } else {
    const d = defaults.date ? new Date(defaults.date + 'T09:00') : new Date(Date.now() + 3600 * 1000);
    if (!defaults.date) d.setMinutes(0, 0, 0);
    f.due_datetime.value = toLocalInput(d);
  }
  openModal('#taskModal');
  f.title.focus();
}

$('#fabAdd').addEventListener('click', () => openTaskModal(null, window.taskDefaults ? window.taskDefaults() : {}));

$('#taskForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = {
    title: f.title.value, description: f.description.value, category: f.category.value,
    priority: f.priority.value, due_datetime: f.due_datetime.value,
    reminder_interval_minutes: Number(f.reminder_interval_minutes.value),
  };
  try {
    await api(editingId ? `/api/tasks/${editingId}` : '/api/tasks', { method: editingId ? 'PUT' : 'POST', body });
    closeModals();
    toast(editingId ? 'Task updated.' : 'Task added.', 'success');
    await refreshAll();
  } catch (err) {
    const box = $('#taskError'); box.textContent = err.message; box.hidden = false;
  }
});

/* ============================ proof upload =========================== */
let proofTaskId = null;

function openProof(id) {
  const t = TASKS.get(Number(id));
  proofTaskId = Number(id);
  $('#proofTask').textContent = t ? `Task: ${t.title}` : '';
  $('#proofForm').reset();
  $('#proofPreview').hidden = true;
  $('#proofHint').hidden = false;
  $('#proofError').hidden = true;
  openModal('#proofModal');
}

$('#proofDrop').addEventListener('click', (e) => { if (e.target.tagName !== 'INPUT') $('#proofFile').click(); });
$('#proofFile').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  $('#proofPreview').src = URL.createObjectURL(file);
  $('#proofPreview').hidden = false;
  $('#proofHint').hidden = true;
});

$('#proofForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = $('#proofFile').files[0];
  const box = $('#proofError');
  box.hidden = true;
  if (!file) { box.textContent = 'Please choose a photo first.'; box.hidden = false; return; }
  if (file.size > 5 * 1024 * 1024) { box.textContent = 'Photo is too large (max 5 MB).'; box.hidden = false; return; }
  const btn = $('#proofSubmit'); btn.disabled = true;
  try {
    const fd = new FormData(); fd.append('photo', file);
    const res = await api(`/api/tasks/${proofTaskId}/proof`, { method: 'POST', body: fd });
    closeModals();
    confetti();
    toast(`Task completed! +${res.reward.points} points 🎉`, 'success');
    await refreshAll();
    if (res.reward.new_unlocks > 0) openModal('#unlockModal');
  } catch (err) {
    box.textContent = err.message; box.hidden = false;
  } finally { btn.disabled = false; }
});

/* ============================ task card ============================== */
function taskCard(t) {
  TASKS.set(t.id, t);
  const cls = { 'Pending': '', 'Awaiting Proof': 'proof', 'Completed': 'done' }[t.status];
  const late = t.overdue ? ' late' : '';
  const prio = t.priority === 'High' ? 'high' : t.priority === 'Low' ? 'low' : '';
  let action = '';
  if (t.status === 'Pending') {
    action = `<button class="btn small primary" data-action="done" data-id="${t.id}">✓ Mark done</button>`;
  } else if (t.status === 'Awaiting Proof') {
    action = `<button class="btn small warn" data-action="proof" data-id="${t.id}">📷 Upload proof</button>`;
  } else if (t.proof_url) {
    action = `<a class="thumb" href="${esc(t.proof_url)}" target="_blank" rel="noopener" title="View proof"><img src="${esc(t.proof_url)}" alt="Proof photo"></a>`;
  }
  const undo = t.status === 'Awaiting Proof' ? `<button class="mini" title="Move back to pending" data-action="reopen" data-id="${t.id}">↩</button>` : '';
  const edit = `<button class="mini" title="Edit" data-action="edit" data-id="${t.id}">✏️</button>`;
  const del = `<button class="mini" title="Delete" data-action="delete" data-id="${t.id}">🗑️</button>`;
  return `
    <article class="task ${cls}${late}">
      <div class="bar"></div>
      <div>
        <div class="t-title">${esc(t.title)}</div>
        ${t.description ? `<div class="t-desc">${esc(t.description)}</div>` : ''}
        <div class="meta">
          <span>🕒 ${esc(fmtDue(t.due_datetime))}</span>
          <span class="badge">${esc(t.category)}</span>
          <span class="badge ${prio}">${esc(t.priority)}</span>
          ${t.status === 'Awaiting Proof' ? '<span class="badge proof">Awaiting proof</span>' : ''}
          ${t.status === 'Completed' ? '<span class="badge done">Completed</span>' : ''}
          ${t.overdue ? '<span class="badge overdue">Overdue</span>' : ''}
          ${t.reminder_interval_minutes && t.status !== 'Completed' ? `<span>🔔 every ${fmtInterval(t.reminder_interval_minutes)}</span>` : ''}
        </div>
      </div>
      <div class="t-actions">${action}<div class="row-actions">${undo}${edit}${del}</div></div>
    </article>`;
}

function emptyState(emoji, text) {
  return `<div class="empty card"><div class="big-emoji">${emoji}</div><p>${text}</p></div>`;
}

document.addEventListener('click', async (e) => {
  const b = e.target.closest('[data-action]');
  if (!b) return;
  const id = Number(b.dataset.id);
  try {
    switch (b.dataset.action) {
      case 'done':
        await api(`/api/tasks/${id}/mark-done`, { method: 'POST' });
        await refreshAll();
        toast('Almost there! Upload a photo of your work to finish the task.', 'info');
        openProof(id);
        break;
      case 'proof': openProof(id); break;
      case 'reopen':
        await api(`/api/tasks/${id}/reopen`, { method: 'POST' });
        await refreshAll();
        break;
      case 'edit': openTaskModal(TASKS.get(id)); break;
      case 'delete':
        if (confirm('Delete this task?')) {
          await api(`/api/tasks/${id}`, { method: 'DELETE' });
          toast('Task deleted.', 'info');
          await refreshAll();
        }
        break;
    }
  } catch (err) { toast(err.message, 'error'); }
});

/* ===================== header, polling & reminders =================== */
async function refreshHeader() {
  const s = await api('/api/rewards/summary');
  window.SUMMARY = s;
  $('#chipPoints').textContent = s.total_points;
  $('#chipStreak').textContent = s.streak.current_streak;
  $('#gameDot').hidden = !(s.game.available > 0 || s.game.active_remaining > 0);
  return s;
}

async function refreshAll() {
  try {
    const s = await refreshHeader();
    if (window.pageRefresh) await window.pageRefresh(s);
    $('#lastUpdated').textContent = 'Updated ' + new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  } catch (err) { console.error(err); }
}

async function checkReminders() {
  try {
    const { reminders } = await api('/api/reminders/due');
    reminders.forEach((r) => {
      const mins = Math.abs(r.minutes_left);
      const span = mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins} min`;
      let msg;
      if (r.status === 'Awaiting Proof') msg = `Upload a photo to finish “${r.title}”.`;
      else if (r.overdue) msg = `“${r.title}” is overdue by ${span}.`;
      else msg = `“${r.title}” is due in ${span}.`;
      toast('🔔 ' + msg, 'reminder', 9000);
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Task reminder', { body: msg });
      }
    });
  } catch (err) { console.error(err); }
}

const bell = $('#bellBtn');
if ('Notification' in window && Notification.permission === 'default') bell.hidden = false;
bell.addEventListener('click', async () => {
  const p = await Notification.requestPermission();
  bell.hidden = p !== 'default';
  if (p === 'granted') toast('Reminder notifications are on.', 'success');
});

$('#themeBtn').addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('theme', next); } catch (_) { /* ignore */ }
});
$('#logoutBtn').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' });
  location.href = '/login';
});

/* =============================== pages =============================== */
function sortForList(tasks) {
  const rank = { 'Awaiting Proof': 0, 'Pending': 1, 'Completed': 2 };
  return [...tasks].sort((a, b) => rank[a.status] - rank[b.status] || a.due_datetime.localeCompare(b.due_datetime));
}

/* ---- Dashboard ---- */
function initDashboard() {
  $('#todayDate').textContent = new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' });
  const h = new Date().getHours();
  const hello = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
  $('#greeting').textContent = $('#greeting').textContent.replace(/^Hello/, hello);

  window.pageRefresh = async (s) => {
    const { tasks } = await api('/api/tasks?scope=today');
    const done = tasks.filter((t) => t.status === 'Completed').length;
    const pct = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
    $('#progressText').textContent = tasks.length ? `${done} of ${tasks.length} tasks done` : 'No tasks today';
    $('#progressPct').textContent = pct + '%';
    $('#progressFill').style.width = pct + '%';
    $('#taskList').innerHTML = tasks.length
      ? sortForList(tasks).map(taskCard).join('')
      : emptyState('🌤️', 'Nothing planned for today. Tap ＋ to add a task.');

    $('#statToday').textContent = s.today.points;
    $('#statStreak').textContent = s.streak.current_streak;
    $('#statTotal').textContent = s.total_points;

    // relaxation break card
    const g = s.game;
    if (g.available > 0 || g.active_remaining > 0) {
      $('#breakCard').innerHTML = `<div><b>🫧 Break unlocked!</b></div><a class="btn small primary" href="/game">Take a break</a>`;
    } else {
      const filled = g.unlock_every - g.next_unlock_in;
      $('#breakCard').innerHTML = `<div class="muted">Next break in <b>${g.next_unlock_in}</b> task${g.next_unlock_in > 1 ? 's' : ''}</div>
        <div class="dots">${Array.from({ length: g.unlock_every }, (_, i) => `<i class="${i < filled ? 'on' : ''}"></i>`).join('')}</div>`;
    }

    // end-of-day reward panel
    const t = s.today, dayEnd = $('#dayEndCard');
    dayEnd.hidden = false;
    if (t.tasks_due === 0) dayEnd.innerHTML = `<b>🎁 Daily bonus:</b> add tasks due today and finish them all to earn +${t.bonus_points} bonus points at the end of the day.`;
    else if (t.all_done) dayEnd.innerHTML = `<b>🎁 All done!</b> You'll receive your +${t.bonus_points} bonus points when the day ends. ${esc(t.message)}`;
    else dayEnd.innerHTML = `<b>🎁 Daily bonus:</b> finish the ${t.tasks_due - t.tasks_due_done} remaining task${t.tasks_due - t.tasks_due_done > 1 ? 's' : ''} due today to earn +${t.bonus_points} bonus points at the end of the day. ${esc(t.message)}`;

    // yesterday's settled reward (shown once)
    const y = s.yesterday, yc = $('#yesterdayCard');
    let seen = null; try { seen = localStorage.getItem('seenReward'); } catch (_) { /* ignore */ }
    if (y && y.tasks_completed > 0 && seen !== y.date) {
      yc.hidden = false;
      yc.innerHTML = `<div><h3>🌙 Yesterday's reward</h3>
        <p>You completed <b>${y.tasks_completed}</b> task${y.tasks_completed > 1 ? 's' : ''} and earned <b>${y.points_earned}</b> points${y.bonus_awarded ? ` — including the <b>+${t.bonus_points} daily bonus</b>! 🎉` : '.'}</p></div>
        <button class="btn small ghost" id="dismissReward">Got it</button>`;
      $('#dismissReward').onclick = () => { try { localStorage.setItem('seenReward', y.date); } catch (_) { /* ignore */ } yc.hidden = true; };
    } else yc.hidden = true;
  };
}

/* ---- Tasks page ---- */
function initTasks() {
  let filter = 'all', query = '', all = [];
  const render = () => {
    let list = all;
    if (filter === 'overdue') list = list.filter((t) => t.overdue);
    else if (filter !== 'all') list = list.filter((t) => t.status === filter);
    if (query) { const q = query.toLowerCase(); list = list.filter((t) => (t.title + t.description + t.category).toLowerCase().includes(q)); }
    $('#taskList').innerHTML = list.length ? sortForList(list).map(taskCard).join('') : emptyState('🗂️', 'No tasks here yet.');
  };
  window.pageRefresh = async () => { all = (await api('/api/tasks')).tasks; render(); };
  $('#filters').addEventListener('click', (e) => {
    const b = e.target.closest('[data-filter]'); if (!b) return;
    filter = b.dataset.filter;
    $$('#filters .chip-btn').forEach((x) => x.classList.toggle('active', x === b));
    render();
  });
  $('#searchBox').addEventListener('input', (e) => { query = e.target.value.trim(); render(); });
}

/* ---- Calendar page ---- */
function initCalendar() {
  let view = 'month', cursor = new Date(), selected = ymd(new Date()), tasks = [];
  const todayStr = ymd(new Date());
  const monthNames = { month: { month: 'long', year: 'numeric' } };

  function range() {
    if (view === 'week') {
      const s = new Date(cursor); s.setDate(s.getDate() - s.getDay());
      const e = new Date(s); e.setDate(e.getDate() + 6);
      return [s, e];
    }
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const last = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0);
    if (view === 'list') return [first, last];
    const s = new Date(first); s.setDate(s.getDate() - s.getDay());
    const e = new Date(last); e.setDate(e.getDate() + (6 - e.getDay()));
    return [s, e];
  }
  const byDay = (d) => tasks.filter((t) => t.due_datetime.slice(0, 10) === d);
  const pillClass = (t) => (t.status === 'Completed' ? 'done' : t.status === 'Awaiting Proof' ? 'proof' : t.overdue ? 'late' : '');

  function title() {
    if (view === 'week') {
      const [s, e] = range();
      return `${s.toLocaleDateString([], { day: 'numeric', month: 'short' })} – ${e.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })}`;
    }
    return cursor.toLocaleDateString([], monthNames.month);
  }

  function render() {
    $('#calTitle').textContent = title();
    const body = $('#calBody');
    $('#dayPanel').hidden = view !== 'month';

    if (view === 'month') {
      const [s, e] = range();
      let html = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => `<div class="cal-dow">${d}</div>`).join('');
      for (let d = new Date(s); d <= e; d.setDate(d.getDate() + 1)) {
        const ds = ymd(d), list = byDay(ds);
        const cls = ['cal-cell', d.getMonth() !== cursor.getMonth() ? 'out' : '', ds === todayStr ? 'today' : '', ds === selected ? 'sel' : ''].join(' ');
        html += `<button class="${cls}" data-day="${ds}"><span class="num">${d.getDate()}</span>
          <span class="pills">${list.slice(0, 8).map((t) => `<i class="pill ${pillClass(t)}"></i>`).join('')}</span>
          ${list.length > 2 ? `<span class="more">${list.length} tasks</span>` : ''}</button>`;
      }
      body.innerHTML = `<div class="cal-grid">${html}</div>`;
      renderDay();
    } else if (view === 'week') {
      const [s] = range();
      let html = '';
      for (let i = 0; i < 7; i++) {
        const d = new Date(s); d.setDate(d.getDate() + i);
        const ds = ymd(d), list = byDay(ds);
        html += `<div class="week-day ${ds === todayStr ? 'today' : ''}"><h3>${d.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' })}
          <button class="btn small ghost" data-add="${ds}">＋</button></h3>
          <div class="task-list">${list.length ? list.map(taskCard).join('') : '<p class="muted small">Nothing planned.</p>'}</div></div>`;
      }
      body.innerHTML = html;
    } else {
      body.innerHTML = tasks.length ? `<div class="task-list">${tasks.map(taskCard).join('')}</div>` : emptyState('📅', 'No tasks this month.');
    }
  }

  function renderDay() {
    const list = byDay(selected);
    $('#dayTitle').textContent = new Date(selected + 'T00:00').toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' });
    $('#dayTasks').innerHTML = list.length ? list.map(taskCard).join('') : '<p class="muted">No tasks on this day.</p>';
  }

  window.taskDefaults = () => ({ date: selected });
  window.pageRefresh = async () => {
    const [s, e] = range();
    tasks = (await api(`/api/calendar?start=${ymd(s)}&end=${ymd(e)}`)).tasks;
    render();
  };

  const move = (dir) => {
    if (view === 'week') cursor.setDate(cursor.getDate() + 7 * dir);
    else cursor = new Date(cursor.getFullYear(), cursor.getMonth() + dir, 1);
    refreshAll();
  };
  $('#calPrev').onclick = () => move(-1);
  $('#calNext').onclick = () => move(1);
  $('#calToday').onclick = () => { cursor = new Date(); selected = todayStr; refreshAll(); };
  $('#viewSwitch').addEventListener('click', (e) => {
    const b = e.target.closest('[data-view]'); if (!b) return;
    view = b.dataset.view;
    $$('#viewSwitch button').forEach((x) => x.classList.toggle('active', x === b));
    refreshAll();
  });
  $('#calBody').addEventListener('click', (e) => {
    const cell = e.target.closest('[data-day]');
    if (cell) { selected = cell.dataset.day; render(); $('#dayPanel').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
    const add = e.target.closest('[data-add]');
    if (add) openTaskModal(null, { date: add.dataset.add });
  });
  $('#dayAdd').onclick = () => openTaskModal(null, { date: selected });
}

/* ---- Rewards page ---- */
function initRewards() {
  window.pageRefresh = async (s) => {
    $('#rTotal').textContent = s.total_points;
    $('#rStreak').textContent = s.streak.current_streak;
    $('#rLongest').textContent = s.streak.longest_streak;
    $('#rDone').textContent = s.streak.total_completed;
    $('#hPer').textContent = s.config.points_per_task;
    $('#hBonus').textContent = s.config.daily_bonus;

    const t = s.today;
    $('#todayReward').innerHTML = `<h3>Today</h3>
      <p>${esc(t.message)}</p>
      <p class="muted">${t.tasks_completed} task${t.tasks_completed === 1 ? '' : 's'} completed · ${t.points} points so far.
      ${t.tasks_due === 0 ? 'Add tasks for today to be eligible for the daily bonus.'
        : t.all_done ? `All of today's tasks are done — your +${t.bonus_points} bonus arrives at the end of the day. 🎁`
        : `${t.tasks_due - t.tasks_due_done} task(s) left for the +${t.bonus_points} end-of-day bonus.`}</p>`;

    const days = [...s.history].reverse();
    const max = Math.max(10, ...days.map((d) => d.points_earned));
    $('#bars').innerHTML = days.length ? days.map((d) => `
      <div class="bar-col"><b>${d.points_earned}</b>
        <div class="b" style="height:${Math.round((d.points_earned / max) * 100)}%" title="${d.tasks_completed} tasks${d.bonus_awarded ? ' + bonus' : ''}"></div>
        <span>${new Date(d.date + 'T00:00').toLocaleDateString([], { weekday: 'short' })}${d.bonus_awarded ? ' 🎁' : ''}</span></div>`).join('')
      : '<p class="muted">Complete your first task to see your progress here.</p>';

    const A = [
      ['🌱', 'First step', 'Complete 1 task', s.streak.total_completed >= 1],
      ['🎯', 'Getting going', 'Complete 10 tasks', s.streak.total_completed >= 10],
      ['🔥', '3-day streak', 'Three days in a row', s.streak.longest_streak >= 3],
      ['⚡', '7-day streak', 'A whole week', s.streak.longest_streak >= 7],
      ['🏅', '100 points', 'Earn 100 points', s.total_points >= 100],
      ['💎', '500 points', 'Earn 500 points', s.total_points >= 500],
    ];
    $('#badges').innerHTML = A.map(([ic, n, d, got]) => `<div class="award ${got ? 'got' : ''}"><div class="ic">${ic}</div><b>${n}</b><small>${d}</small></div>`).join('');
  };
}

/* ============================== start ================================ */
({ dashboard: initDashboard, tasks: initTasks, calendar: initCalendar, rewards: initRewards }[PAGE] || (() => {}))();
refreshAll();
checkReminders();
setInterval(refreshAll, 45000);          // frequent updates without reloading the page
setInterval(checkReminders, 60000);      // reminder check every minute
document.addEventListener('visibilitychange', () => { if (!document.hidden) { refreshAll(); checkReminders(); } });

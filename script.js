/* script.js — TaskFlow frontend logic */
'use strict';

const API = 'http://127.0.0.1:8000';

// ── In-memory caches ──────────────────────────────────────────────────────────
let _projects = [];
let _users = [];
let _tasks = [];
let _activeRequests = 0; // Track number of active API requests
let _loadingTimer = null;

// ── Loading indicator helpers ─────────────────────────────────────────────────
function showLoading() {
  _activeRequests++;

    // Only start the timer for the first active request

  if (_activeRequests === 1) {
    _loadingTimer = setTimeout(() => {

      const overlay = document.getElementById('loading-overlay');
      if (overlay) overlay.classList.add('show');
    }, 500);  // Show loader only if request takes more than 500ms
  }
}

function hideLoading() {
  _activeRequests = Math.max(0, _activeRequests - 1);
  if (_activeRequests === 0) {

    clearTimeout(_loadingTimer);
    _loadingTimer = null;
    
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.remove('show');
  }
}

// ── Utility: fetch wrapper ────────────────────────────────────────────────────
/**
 * Thin wrapper around fetch() that:
 *  - Sets JSON headers automatically
 *  - Throws a human-readable Error on non-2xx responses
 *  - Returns null for 204 No Content
 *  - Shows/hides loading indicator
 */
async function api(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    // Always hit the server for fresh data. Relying on server cache headers
    // alone previously caused deleted/updated rows to keep showing in the UI
    // for up to 30s (or until a manual refresh) because the browser served a
    // stale cached GET response instead of re-fetching after a mutation.
    cache: 'no-store',
  };
  if (body !== undefined) opts.body = JSON.stringify(body);

  showLoading();
  try {
    const res = await fetch(API + path, opts);

    if (res.status === 204) return null;

    const data = await res.json();

    if (!res.ok) {
      // FastAPI returns validation errors as an array in data.detail
      const msg = data?.detail
        ? (Array.isArray(data.detail)
          ? data.detail.map(e => e.msg).join(', ')
          : data.detail)
        : `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  } finally {
    hideLoading();
  }
}

// ── Toast notification ────────────────────────────────────────────────────────
let _toastTimer;
function toast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 3500);
}

// ── Debounce utility ──────────────────────────────────────────────────────────
/**
 * Debounce function to limit how often a function is called.
 * @param {Function} func - Function to debounce
 * @param {number} wait - Milliseconds to wait before calling func
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// ── Modal helpers ─────────────────────────────────────────────────────────────
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }
function closeOnOverlay(e, id) { if (e.target === e.currentTarget) closeModal(id); }

// ── Open project modal (ensure users loaded first) ────────────────────────────
async function openProjectModal() {
  // If owner dropdown is empty, load users first
  if (_users.length === 0) {
    await loadUsers(/* silent */ true);
  }
  openModal('modal-project');
}

// ── Open task modal (ensure projects loaded first) ────────────────────────────
async function openTaskModal() {
  // If project dropdown is empty, load projects first
  if (_projects.length === 0) {
    await loadProjects();
  }
  openModal('modal-task');
}

// ── Open quick-add modal (ensure projects loaded first) ────────────────────────
async function openQuickAddModal() {
  if (_projects.length === 0) {
    await loadProjects();
  }
  openModal('modal-quickadd');
}

// ── View switching ────────────────────────────────────────────────────────────
function showView(name, btn) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('view-' + name).classList.add('active');
  btn.classList.add('active');

  if (name === 'dashboard') loadDashboard();
  if (name === 'projects') loadProjects();
  if (name === 'tasks') loadTasksView();   // uses dedicated view-loader
  if (name === 'users') loadUsers();
}

// ── Badge helpers ─────────────────────────────────────────────────────────────
function statusBadge(s) {
  const map = { todo: 'todo', in_progress: 'progress', done: 'done' };
  const label = { todo: 'To Do', in_progress: 'In Progress', done: 'Done' };
  return `<span class="badge badge-${map[s] || 'todo'}">${label[s] || s}</span>`;
}
function priorityBadge(p) {
  if (!p) return '<span class="badge">—</span>';
  return `<span class="badge badge-${p}">${p.charAt(0).toUpperCase() + p.slice(1)}</span>`;
}

// ── API status indicator ──────────────────────────────────────────────────────
function setApiStatus(online) {
  const el = document.getElementById('api-status');
  el.className = 'status-dot ' + (online ? 'online' : 'offline');
  el.title = online ? 'API Online' : 'API Offline';
}

// ═════════════════════════════════════════════════════════════════════════════
// Dashboard
// ═════════════════════════════════════════════════════════════════════════════

// In-memory cache of the last /stats response. Every mutation (create/update/
// delete of a task, project, or user) calls invalidateStatsCache() so the
// next dashboard visit always fetches fresh data — but simply switching
// tabs back and forth with no changes in between reuses the cached result
// instead of re-hitting the network every time.
let _statsCache = null;

function invalidateStatsCache() {
  _statsCache = null;
}

async function loadDashboard() {
  if (_statsCache) {
    renderDashboardStats(_statsCache);
    setApiStatus(true);
    return;
  }
  try {
    const stats = await api('GET', '/stats');
    _statsCache = stats;
    renderDashboardStats(stats);
    setApiStatus(true);
  } catch (err) {
    toast('Could not load dashboard: ' + err.message, 'error');
    setApiStatus(false);
  }
}

function renderDashboardStats(stats) {
  const totals = stats.reduce(
    (acc, s) => {
      acc.tasks += s.total_tasks;
      acc.todo += s.todo;
      acc.progress += s.in_progress;
      acc.done += s.done;
      return acc;
    },
    { tasks: 0, todo: 0, progress: 0, done: 0 }
  );

  document.getElementById('s-projects').textContent = stats.length;
  document.getElementById('s-tasks').textContent = totals.tasks;
  document.getElementById('s-todo').textContent = totals.todo;
  document.getElementById('s-progress').textContent = totals.progress;
  document.getElementById('s-done').textContent = totals.done;

  const tbody = document.getElementById('stats-body');
  tbody.innerHTML = stats.map(s => {
    const pct = s.total_tasks ? Math.round((s.done / s.total_tasks) * 100) : 0;
    return `<tr>
      <td><strong>${esc(s.project_name)}</strong></td>
      <td>${s.total_tasks}</td>
      <td><span style="color:var(--todo)">${s.todo}</span></td>
      <td><span style="color:var(--progress)">${s.in_progress}</span></td>
      <td><span style="color:var(--done)">${s.done}</span></td>
      <td>
        <div style="display:flex;align-items:center;gap:8px">
          <div class="prog-bar-wrap">
            <div class="prog-bar" style="width:${pct}%"></div>
          </div>
          <span style="font-size:11px;color:var(--muted)">${pct}%</span>
        </div>
      </td>
    </tr>`;
  }).join('');
}

// ═════════════════════════════════════════════════════════════════════════════
// Projects
// ═════════════════════════════════════════════════════════════════════════════
async function loadProjects() {
  try {
    // Ensure users are loaded first so we can display owner names
    if (_users.length === 0) {
      await loadUsers(/* silent */ true);
    }
    _projects = await api('GET', '/projects');
    renderProjectsTable();
    populateProjectSelects();
  } catch (err) {
    toast('Could not load projects: ' + err.message, 'error');
  }
}

function renderProjectsTable() {
  const bodyEl = document.getElementById('projects-body');
  if (!bodyEl) return;
  // Build a user-id → name lookup for the owner column
  const userMap = Object.fromEntries(_users.map(u => [u.id, u.name]));

  bodyEl.innerHTML = _projects.length === 0
    ? '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px">No projects yet.</td></tr>'
    : _projects.map(p => `
    <tr>
      <td>${p.id}</td>
      <td><strong>${esc(p.name)}</strong></td>
      <td>${esc(p.description || '—')}</td>
      <td>${esc(userMap[p.owner_id] || String(p.owner_id))}</td>
      <td>
        <button class="btn-icon" title="Delete project" onclick="deleteProject(${p.id})">🗑️</button>
      </td>
    </tr>
  `).join('');
}

async function submitProject(e) {
  e.preventDefault();
  const ownerId = parseInt(document.getElementById('p-owner').value);
  if (!ownerId) { toast('Please select an owner', 'error'); return; }
  try {
    await api('POST', '/projects', {
      name: document.getElementById('p-name').value.trim(),
      description: document.getElementById('p-desc').value.trim() || null,
      owner_id: ownerId,
    });
    closeModal('modal-project');
    e.target.reset();
    toast('Project created ✓');
    await loadProjects();
    // Update project dropdowns in task modals immediately
    populateProjectSelects();
    invalidateStatsCache();
    // Reload dashboard now if it's currently visible (otherwise the
    // invalidated cache ensures a fresh fetch next time it's opened)
    if (document.getElementById('view-dashboard').classList.contains('active')) {
      loadDashboard();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function deleteProject(id) {
  if (!confirm('Delete this project and all its tasks?')) return;
  try {
    await api('DELETE', `/projects/${id}`);
    toast('Project deleted');
    await loadProjects();
    // Update project dropdowns in task modals
    populateProjectSelects();
    // Reload tasks if viewing tasks (they might be filtered by deleted project)
    if (document.getElementById('view-tasks').classList.contains('active')) {
      await loadTasks();
    }
    invalidateStatsCache();
    // Reload dashboard now if it's currently visible (otherwise the
    // invalidated cache ensures a fresh fetch next time it's opened)
    if (document.getElementById('view-dashboard').classList.contains('active')) {
      loadDashboard();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
}

/**
 * Populate the project dropdowns used in:
 *  - Task creation modal (#t-project)
 *  - Task filter bar (#filter-project)
 */
function populateProjectSelects() {
  const selects = ['t-project', 'qa-project', 'filter-project'];
  selects.forEach(sid => {
    const sel = document.getElementById(sid);
    if (!sel) return; // guard in case a select isn't in the DOM yet
    const prev = sel.value;   // remember previous selection

    if (sid === 'filter-project') {
      sel.innerHTML = '<option value="">All Projects</option>';
    } else {
      sel.innerHTML = '';
    }

    _projects.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      sel.appendChild(opt);
    });

    // Restore the previous selection if it still exists
    if (prev) sel.value = prev;
  });
}

// ═════════════════════════════════════════════════════════════════════════════
// Tasks
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Called when the Tasks nav button is clicked.
 * Ensures projects are loaded first so the filter dropdown and
 * the project-name column both render correctly.
 */
async function loadTasksView() {
  // Tasks and projects are independent GET requests — fetching tasks does
  // not depend on projects being loaded first, only *rendering* the
  // project-name column does. Running them in parallel (instead of the
  // previous await-then-await chain) roughly halves the wait on first
  // visit to this view. If projects are already cached, we skip straight
  // to loading tasks.
  if (_projects.length === 0) {
    await Promise.all([loadProjects(), loadTasks()]);
  } else {
    await loadTasks();
  }
}

/**
 * Fetch tasks from the API (optionally filtered by project) and re-render.
 * Also called by the filter-project dropdown's onchange.
 */
async function loadTasks() {
  const pid = document.getElementById('filter-project').value;
  try {
    const url = pid ? `/tasks?project_id=${pid}` : '/tasks';
    _tasks = await api('GET', url);
    renderTasksTable();
  } catch (err) {
    toast('Could not load tasks: ' + err.message, 'error');
  }
}

function renderTasksTable() {
  // Guard: tasks view elements may not be in the DOM if called before view loads
  const statusEl = document.getElementById('filter-status');
  const priorityEl = document.getElementById('filter-priority');
  const searchEl = document.getElementById('search-tasks');
  const sortEl = document.getElementById('sort-tasks');
  const bodyEl = document.getElementById('tasks-body');
  if (!statusEl || !priorityEl || !searchEl || !sortEl || !bodyEl) return;

  const statusFilter = statusEl.value;
  const priorityFilter = priorityEl.value;
  const searchQuery = (searchEl.value || '').trim().toLowerCase();
  const sortKey = sortEl.value;

  // ── Priority order map (used for sorting) ────────────────────────────────
  const PRIORITY_ORDER = { high: 0, medium: 1, low: 2 };
  const STATUS_ORDER = { todo: 0, in_progress: 1, done: 2 };

  // ── 1. Filter ─────────────────────────────────────────────────────────────
  let result = _tasks.filter(t => {
    if (statusFilter && t.status !== statusFilter) return false;
    if (priorityFilter && t.priority !== priorityFilter) return false;
    // Search: match against title and description (case-insensitive)
    if (searchQuery) {
      const inTitle = t.title.toLowerCase().includes(searchQuery);
      const inDesc = (t.description || '').toLowerCase().includes(searchQuery);
      if (!inTitle && !inDesc) return false;
    }
    return true;
  });

  // ── 2. Sort ───────────────────────────────────────────────────────────────
  if (sortKey) {
    result = [...result].sort((a, b) => {
      switch (sortKey) {
        case 'title-asc':
          return a.title.localeCompare(b.title);
        case 'title-desc':
          return b.title.localeCompare(a.title);
        case 'priority-high':
          return (PRIORITY_ORDER[a.priority] ?? 99) - (PRIORITY_ORDER[b.priority] ?? 99);
        case 'priority-low':
          return (PRIORITY_ORDER[b.priority] ?? 99) - (PRIORITY_ORDER[a.priority] ?? 99);
        case 'status-asc':
          return (STATUS_ORDER[a.status] ?? 99) - (STATUS_ORDER[b.status] ?? 99);
        case 'status-done':
          return (STATUS_ORDER[b.status] ?? 99) - (STATUS_ORDER[a.status] ?? 99);
        case 'due-asc': {
          const da = a.due_date ? new Date(a.due_date) : Infinity;
          const db_ = b.due_date ? new Date(b.due_date) : Infinity;
          return da - db_;
        }
        case 'due-desc': {
          const da = a.due_date ? new Date(a.due_date) : -Infinity;
          const db_ = b.due_date ? new Date(b.due_date) : -Infinity;
          return db_ - da;
        }
        case 'id-desc':
          return b.id - a.id;
        case 'id-asc':
          return a.id - b.id;
        default:
          return 0;
      }
    });
  }

  // ── 3. Build project-id → project-name lookup ─────────────────────────────
  const projMap = Object.fromEntries(_projects.map(p => [p.id, p.name]));

  // ── 4. Render ─────────────────────────────────────────────────────────────
  if (result.length === 0) {
    const msg = searchQuery
      ? `No tasks match "<strong>${esc(searchQuery)}</strong>".`
      : 'No tasks found.';
    document.getElementById('tasks-body').innerHTML =
      `<tr><td colspan="7" style="text-align:center;color:var(--muted);padding:24px">${msg}</td></tr>`;
    return;
  }

  document.getElementById('tasks-body').innerHTML = result.map(t => {
    // Highlight matching text in title
    const titleHtml = searchQuery
      ? highlightMatch(esc(t.title), searchQuery)
      : `<strong>${esc(t.title)}</strong>`;
    return `
      <tr>
        <td>${t.id}</td>
        <td>${titleHtml}</td>
        <td>${esc(projMap[t.project_id] || String(t.project_id))}</td>
        <td>${statusBadge(t.status)}</td>
        <td>${priorityBadge(t.priority)}</td>
        <td>${esc(t.due_date || '—')}</td>
        <td>
          <button class="btn-icon" title="Edit task"   onclick="openEditTask(${t.id})">✏️</button>
          <button class="btn-icon" title="Delete task" onclick="deleteTask(${t.id})">🗑️</button>
        </td>
      </tr>`;
  }).join('');
}

/**
 * Wraps matched portions of `text` (already HTML-escaped) in a highlight span.
 * Works on the escaped string so it is safe against XSS.
 * @param {string} escapedText  - HTML-escaped task title
 * @param {string} query        - raw search query (lowercase)
 */
function highlightMatch(escapedText, query) {
  // Escape regex special characters in the query
  const safeQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`(${safeQuery})`, 'gi');
  return '<strong>' + escapedText.replace(re, '<mark class="search-highlight">$1</mark>') + '</strong>';
}

async function submitTask(e) {
  e.preventDefault();
  const projId = parseInt(document.getElementById('t-project').value);
  if (!projId) { toast('Please select a project', 'error'); return; }
  try {
    await api('POST', '/tasks', {
      title: document.getElementById('t-title').value.trim(),
      description: document.getElementById('t-desc').value.trim() || null,
      project_id: projId,
      status: document.getElementById('t-status').value,
      priority: document.getElementById('t-priority').value,
      due_date: document.getElementById('t-due').value.trim() || null,
    });
    closeModal('modal-task');
    e.target.reset();
    toast('Task created ✓');
    await loadTasks();
    invalidateStatsCache();
    // Reload dashboard now if it's currently visible (otherwise the
    // invalidated cache ensures a fresh fetch next time it's opened)
    if (document.getElementById('view-dashboard').classList.contains('active')) {
      loadDashboard();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function submitQuickAdd(e) {
  e.preventDefault();
  const projId = parseInt(document.getElementById('qa-project').value);
  if (!projId) { toast('Please select a project', 'error'); return; }
  const description = document.getElementById('qa-desc').value.trim();
  if (!description) { toast('Please describe the task', 'error'); return; }

  try {
    const task = await api('POST', '/tasks/quick-add', {
      description,
      project_id: projId,
    });
    closeModal('modal-quickadd');
    e.target.reset();

    const dueText = task.due_date ? ` — due ${task.due_date}` : '';
    toast(`Added "${task.title}" (${task.priority} priority)${dueText} ✓`);

    // Only reload tasks if the tasks view is currently visible
    if (document.getElementById('view-tasks').classList.contains('active')) {
      await loadTasks();
    }
    invalidateStatsCache();
    // Reload dashboard now if it's currently visible (otherwise the
    // invalidated cache ensures a fresh fetch next time it's opened)
    if (document.getElementById('view-dashboard').classList.contains('active')) {
      loadDashboard();
    }
  } catch (err) {
    toast('Quick add failed: ' + err.message, 'error');
  }
}

function openEditTask(id) {
  const task = _tasks.find(t => t.id === id);
  if (!task) { toast('Task not found', 'error'); return; }
  document.getElementById('et-id').value = task.id;
  document.getElementById('et-title').value = task.title;
  document.getElementById('et-desc').value = task.description || '';
  document.getElementById('et-status').value = task.status;
  document.getElementById('et-priority').value = task.priority;
  document.getElementById('et-due').value = task.due_date || '';
  openModal('modal-edit-task');
}

async function submitEditTask(e) {
  e.preventDefault();
  const id = parseInt(document.getElementById('et-id').value);
  try {
    await api('PUT', `/tasks/${id}`, {
      title: document.getElementById('et-title').value.trim(),
      description: document.getElementById('et-desc').value.trim() || null,
      status: document.getElementById('et-status').value,
      priority: document.getElementById('et-priority').value,
      due_date: document.getElementById('et-due').value.trim() || null,
    });
    closeModal('modal-edit-task');
    toast('Task updated ✓');
    await loadTasks();
    invalidateStatsCache();
    // Reload dashboard now if it's currently visible (otherwise the
    // invalidated cache ensures a fresh fetch next time it's opened)
    if (document.getElementById('view-dashboard').classList.contains('active')) {
      loadDashboard();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function deleteTask(id) {
  if (!confirm('Delete this task?')) return;
  try {
    await api('DELETE', `/tasks/${id}`);
    toast('Task deleted');
    await loadTasks();
    invalidateStatsCache();
    // Reload dashboard now if it's currently visible (otherwise the
    // invalidated cache ensures a fresh fetch next time it's opened)
    if (document.getElementById('view-dashboard').classList.contains('active')) {
      loadDashboard();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// Users
// ═════════════════════════════════════════════════════════════════════════════

/**
 * Load users from the API and render the users table.
 * @param {boolean} silent - If true, don't show error toasts (used during init)
 */
async function loadUsers(silent = false) {
  try {
    _users = await api('GET', '/users');
    renderUsersTable();
    populateOwnerSelect();
    return true;
  } catch (err) {
    if (!silent) toast('Could not load users: ' + err.message, 'error');
    return false;
  }
}

function renderUsersTable() {
  const bodyEl = document.getElementById('users-body');
  if (!bodyEl) return;
  bodyEl.innerHTML = _users.length === 0
    ? '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:24px">No users yet.</td></tr>'
    : _users.map(u => `
        <tr>
          <td>${u.id}</td>
          <td>${esc(u.name)}</td>
          <td>${esc(u.email)}</td>
          <td>
            <button class="btn-icon" title="Delete user" onclick="deleteUser(${u.id})">🗑️</button>
          </td>
        </tr>
      `).join('');
}

function populateOwnerSelect() {
  const sel = document.getElementById('p-owner');
  sel.innerHTML = '<option value="">Select owner…</option>';
  _users.forEach(u => {
    const opt = document.createElement('option');
    opt.value = u.id;
    opt.textContent = `${u.name} (${u.email})`;
    sel.appendChild(opt);
  });
}

async function submitUser(e) {
  e.preventDefault();
  try {
    await api('POST', '/users', {
      name: document.getElementById('u-name').value.trim(),
      email: document.getElementById('u-email').value.trim(),
      password: document.getElementById('u-password').value,
    });
    closeModal('modal-user');
    e.target.reset();
    toast('User created ✓');
    await loadUsers();
    // Update project owner dropdown immediately
    populateOwnerSelect();
    // If currently viewing projects, re-render to show updated owner names
    if (document.getElementById('view-projects').classList.contains('active')) {
      renderProjectsTable();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function deleteUser(id) {
  if (!confirm('Delete this user? Their projects and tasks will also be deleted.')) return;
  try {
    await api('DELETE', `/users/${id}`);
    toast('User deleted');
    await loadUsers();
    // Update dropdowns and projects view
    populateOwnerSelect();
    // Reload projects if viewing projects (owner names might have changed)
    if (document.getElementById('view-projects').classList.contains('active')) {
      await loadProjects();
    }
    invalidateStatsCache();
    // Reload dashboard now if it's currently visible (otherwise the
    // invalidated cache ensures a fresh fetch next time it's opened)
    if (document.getElementById('view-dashboard').classList.contains('active')) {
      loadDashboard();
    }
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── HTML escape (prevents XSS when rendering user data into the page) ─────────
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── Initialise ────────────────────────────────────────────────────────────────
(async function init() {
  // Pre-load users + projects so modals are already populated when the user
  // opens them for the first time, without an extra API round-trip.
  try {
    [_users, _projects] = await Promise.all([
      api('GET', '/users'),
      api('GET', '/projects'),
    ]);
    populateOwnerSelect();
    populateProjectSelects();
    renderUsersTable();          // populate users table if it's already visible
    setApiStatus(true);
  } catch (err) {
    // Show a visible warning instead of silently ignoring the error
    toast('Could not reach the API. Is the backend running?', 'error');
    setApiStatus(false);
  }

  // Apply debouncing to search input for better performance
  const searchInput = document.getElementById('search-tasks');
  if (searchInput) {
    // Remove inline oninput handler and use debounced version
    searchInput.removeAttribute('oninput');
    const debouncedSearch = debounce(renderTasksTable, 300);
    searchInput.addEventListener('input', debouncedSearch);
  }

  // Load the default dashboard view
  loadDashboard();
})();
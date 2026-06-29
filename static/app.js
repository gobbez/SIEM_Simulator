// SIEM Dashboard frontend
const API = {
    health: () => fetch('/api/health').then(r => r.json()),
    filters: () => fetch('/api/filters').then(r => r.json()),
    insights: (params) => fetch('/api/insights?' + new URLSearchParams(params)).then(r => r.json()),
    events: (params) => fetch('/api/events?' + new URLSearchParams(params)).then(r => r.json()),
    event: (id) => fetch(`/api/events/${id}`).then(r => r.json()),
    classify: (id, label) => fetch(`/api/events/${id}/classify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label }),
    }).then(r => r.json()),
};

// State
let state = {
    filters: {},
    page: 1,
    perPage: 50,
    charts: {},
};

const COLORS = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#eab308',
    low: '#22c55e',
    informational: '#06b6d4',
    primary: '#3b82f6',
    purple: '#8b5cf6',
    pink: '#ec4899',
    teal: '#14b8a6',
    slate: '#64748b',
};

const PALETTE = Object.values(COLORS).filter(c => c !== COLORS.critical && c !== COLORS.high);

function init() {
    loadFilters();
    loadDashboard();
    bindEvents();
}

function bindEvents() {
    document.getElementById('refreshBtn').addEventListener('click', loadDashboard);
    document.getElementById('applyFilters').addEventListener('click', applyFilters);
    document.getElementById('resetFilters').addEventListener('click', resetFilters);
    document.getElementById('prevPage').addEventListener('click', () => changePage(-1));
    document.getElementById('nextPage').addEventListener('click', () => changePage(1));
    document.getElementById('closeModal').addEventListener('click', closeModal);
    document.getElementById('modal').addEventListener('click', e => {
        if (e.target.id === 'modal') closeModal();
    });
}

// ---------- Filters ----------

async function loadFilters() {
    try {
        const data = await API.filters();
        fillSelect('severity', data.severity);
        fillSelect('event_type', data.event_type);
        fillSelect('source', data.source);
        fillSelect('user', data.user);
    } catch (e) {
        console.error('Failed to load filters', e);
    }
}

function fillSelect(id, values) {
    const sel = document.getElementById(id);
    sel.innerHTML = '';
    values.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        sel.appendChild(opt);
    });
}

function getSelectedValues(id) {
    return Array.from(document.getElementById(id).selectedOptions).map(o => o.value);
}

function buildParams() {
    const p = {};
    const q = document.getElementById('q').value.trim();
    if (q) p.q = q;

    ['severity', 'event_type', 'source'].forEach(key => {
        const vals = getSelectedValues(key);
        if (vals.length) p[key] = vals.join(',');
    });

    const fromVal = document.getElementById('from').value;
    const toVal = document.getElementById('to').value;
    if (fromVal) p.from = new Date(fromVal).toISOString();
    if (toVal) p.to = new Date(toVal).toISOString();

    return p;
}

function applyFilters() {
    state.filters = buildParams();
    state.page = 1;
    loadDashboard();
}

function resetFilters() {
    ['severity', 'event_type', 'source'].forEach(id => {
        Array.from(document.getElementById(id).options).forEach(o => o.selected = false);
    });
    document.getElementById('q').value = '';
    document.getElementById('from').value = '';
    document.getElementById('to').value = '';
    state.filters = {};
    state.page = 1;
    loadDashboard();
}

// ---------- Loading ----------

async function loadDashboard() {
    updateHealth('Loading…');
    try {
        const [health, insights, events] = await Promise.all([
            API.health(),
            API.insights(state.filters),
            API.events({ ...state.filters, page: state.page, per_page: state.perPage })
        ]);
        updateHealth(`OK • ${health.rows.toLocaleString()} rows`);
        renderKPIs(insights.kpis);
        renderCharts(insights);
        renderEvents(events);
    } catch (e) {
        console.error(e);
        updateHealth('Error', true);
    }
}

function updateHealth(text, error = false) {
    const el = document.getElementById('health');
    el.textContent = text;
    el.className = 'badge ' + (error ? '' : 'ok');
}

// ---------- KPIs ----------

function renderKPIs(kpis) {
    document.getElementById('kpi-total').textContent = kpis.total_events.toLocaleString();
    document.getElementById('kpi-critical').textContent = kpis.critical_events.toLocaleString();
    document.getElementById('kpi-high').textContent = kpis.high_events.toLocaleString();
    document.getElementById('kpi-anomalies').textContent = kpis.anomalies.toLocaleString();
    document.getElementById('kpi-users').textContent = kpis.unique_users.toLocaleString();
    document.getElementById('kpi-srcips').textContent = kpis.unique_src_ips.toLocaleString();
    document.getElementById('kpi-risk').textContent = kpis.avg_risk_score;
}

// ---------- Charts ----------

function renderCharts(data) {
    renderPie('severityChart', 'Severity', data.severity, {
        critical: COLORS.critical,
        high: COLORS.high,
        medium: COLORS.medium,
        low: COLORS.low,
        informational: COLORS.informational,
    });
    renderPie('eventTypeChart', 'Event Type', data.event_type);
    renderBar('sourceChart', 'Source', data.source, true);
    renderBar('userChart', 'User', data.top_users, true);
    renderBar('actionChart', 'Action', data.top_actions, true);
    renderBar('geoChart', 'Geo', data.geo_location, true);
    renderBar('riskChart', 'Risk', data.risk_distribution, false);
    renderTimeline(data.timeline);
    renderAnomalyTimeline(data.anomaly_timeline);
}

function chartCommon(title) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { labels: { color: '#9ca3af', font: { size: 11 } } },
            tooltip: {
                backgroundColor: '#1f2937',
                titleColor: '#e5e7eb',
                bodyColor: '#e5e7eb',
                borderColor: '#2a3441',
                borderWidth: 1,
            },
        },
    };
}

function destroyChart(id) {
    if (state.charts[id]) {
        state.charts[id].destroy();
        delete state.charts[id];
    }
}

function renderPie(id, title, items, colorMap = {}) {
    destroyChart(id);
    const ctx = document.getElementById(id).getContext('2d');
    const labels = items.map(i => i.name);
    const values = items.map(i => i.value);
    const bg = labels.map((l, i) => colorMap[l.toLowerCase()] || PALETTE[i % PALETTE.length]);
    state.charts[id] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: bg,
                borderColor: '#111827',
                borderWidth: 2,
            }]
        },
        options: chartCommon(title),
    });
}

function renderBar(id, title, items, horizontal = false) {
    destroyChart(id);
    const ctx = document.getElementById(id).getContext('2d');
    const labels = items.map(i => i.name);
    const values = items.map(i => i.value);
    state.charts[id] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Count',
                data: values,
                backgroundColor: COLORS.primary,
                borderRadius: 4,
            }]
        },
        options: {
            ...chartCommon(title),
            indexAxis: horizontal ? 'y' : 'x',
            scales: {
                x: { ticks: { color: '#9ca3af' }, grid: { color: '#2a3441' } },
                y: { ticks: { color: '#9ca3af' }, grid: { color: '#2a3441' } },
            },
        },
    });
}

function renderTimeline(timeline) {
    destroyChart('timelineChart');
    const ctx = document.getElementById('timelineChart').getContext('2d');
    state.charts['timelineChart'] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: timeline.map(t => new Date(t.time).toLocaleString()),
            datasets: [{
                label: 'Events',
                data: timeline.map(t => t.count),
                borderColor: COLORS.primary,
                backgroundColor: 'rgba(59,130,246,0.15)',
                fill: true,
                tension: 0.3,
                pointRadius: 2,
            }]
        },
        options: {
            ...chartCommon('Events over time'),
            scales: {
                x: { ticks: { color: '#9ca3af', maxTicksLimit: 8 }, grid: { color: '#2a3441' } },
                y: { ticks: { color: '#9ca3af' }, grid: { color: '#2a3441' } },
            },
        },
    });
}

function renderAnomalyTimeline(data) {
    destroyChart('anomalyChart');
    const ctx = document.getElementById('anomalyChart').getContext('2d');
    state.charts['anomalyChart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => new Date(d.time).toLocaleString()),
            datasets: [
                {
                    label: 'Normal',
                    data: data.map(d => d.normal),
                    backgroundColor: COLORS.low,
                },
                {
                    label: 'Anomaly',
                    data: data.map(d => d.anomaly),
                    backgroundColor: COLORS.critical,
                }
            ]
        },
        options: {
            ...chartCommon('Anomaly timeline'),
            scales: {
                x: { stacked: true, ticks: { color: '#9ca3af', maxTicksLimit: 8 }, grid: { color: '#2a3441' } },
                y: { stacked: true, ticks: { color: '#9ca3af' }, grid: { color: '#2a3441' } },
            },
        },
    });
}

// ---------- Events table ----------

function renderEvents(data) {
    const tbody = document.querySelector('#eventsTable tbody');
    tbody.innerHTML = '';

    if (!data.events.length) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:#9ca3af;padding:24px;">No events found</td></tr>';
    } else {
        data.events.forEach(ev => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${formatTime(ev.timestamp)}</td>
                <td><span class="severity severity-${ev.severity}">${ev.severity}</span></td>
                <td>${ev.event_type}</td>
                <td title="${ev.source}">${truncate(ev.source, 22)}</td>
                <td>${ev.user || '-'}</td>
                <td>${ev.action || '-'}</td>
                <td title="${ev.object || ''}">${truncate(ev.object, 28)}</td>
                <td>${ev.src_ip || ev.dst_ip || '-'}</td>
                <td>${ev.risk_score != null ? ev.risk_score.toFixed(2) : '-'}</td>
                <td>${ev.anomaly ? '<span class="pill" style="color:#ef4444">Yes</span>' : '<span class="pill">No</span>'}</td>
            `;
            tr.addEventListener('click', () => openEvent(ev.event_id));
            tbody.appendChild(tr);
        });
    }

    document.getElementById('pageInfo').textContent = `Page ${data.page} of ${data.pages} (${data.total.toLocaleString()} total)`;
    document.getElementById('prevPage').disabled = data.page <= 1;
    document.getElementById('nextPage').disabled = data.page >= data.pages;
}

function changePage(delta) {
    state.page += delta;
    if (state.page < 1) state.page = 1;
    loadEventsOnly();
}

async function loadEventsOnly() {
    const data = await API.events({ ...state.filters, page: state.page, per_page: state.perPage });
    renderEvents(data);
}

// ---------- Modal ----------

async function openEvent(id) {
    const ev = await API.event(id);
    const body = document.getElementById('modalBody');

    const nestedFields = ['advanced_metadata', 'behavioral_analytics'];
    const ignore = ['index'];

    let html = '<div class="kv-grid">';
    Object.entries(ev).forEach(([key, val]) => {
        if (ignore.includes(key)) return;
        if (key === 'raw_log') return;
        const display = formatValue(val);
        html += `
            <div class="kv ${nestedFields.includes(key) || String(display).length > 40 ? 'full' : ''}">
                <div class="kv-key">${key}</div>
                <div class="kv-value">${display}</div>
            </div>
        `;
    });
    html += '</div>';

    if (ev.raw_log) {
        html += `<h3 style="margin-top:20px;font-size:13px;color:#9ca3af">Raw Log</h3>
                 <pre class="raw-log">${escapeHtml(ev.raw_log)}</pre>`;
    }

    html += renderClassificationSection(ev);

    body.innerHTML = html;
    document.getElementById('modal').classList.remove('hidden');
}

function renderClassificationSection(ev) {
    const already = ev.user_label || '';
    const disabled = already ? 'disabled' : '';
    return `
        <div class="classification">
            <h3>Triage this event</h3>
            <div class="classification-buttons">
                <button class="btn classification-btn fp ${disabled}" data-label="False Positive" data-id="${ev.event_id}" ${disabled}>False Positive</button>
                <button class="btn classification-btn tp ${disabled}" data-label="True Positive" data-id="${ev.event_id}" ${disabled}>True Positive</button>
                <button class="btn classification-btn na ${disabled}" data-label="No Action" data-id="${ev.event_id}" ${disabled}>No Action</button>
            </div>
            <div id="classification-result" class="classification-result">
                ${already ? `You classified this event as <strong>${already}</strong>.` : 'Choose a label above.'}
            </div>
        </div>
    `;
}

async function handleClassificationClick(e) {
    const btn = e.target.closest('.classification-btn');
    if (!btn || btn.disabled) return;

    const id = btn.dataset.id;
    const label = btn.dataset.label;
    const resultEl = document.getElementById('classification-result');

    resultEl.innerHTML = 'Checking...';
    try {
        const res = await API.classify(id, label);
        if (res.error) {
            resultEl.innerHTML = `<span class="error">${escapeHtml(res.error)}</span>`;
            return;
        }
        const statusClass = res.correct ? 'correct' : 'wrong';
        const statusText = res.correct ? '✓ Correct' : `✗ Wrong — the correct label was <strong>${escapeHtml(res.true_label)}</strong>`;
        resultEl.innerHTML = `
            <div class="classification-status ${statusClass}">${statusText}</div>
            <div class="classification-summary">You chose: <strong>${escapeHtml(res.label)}</strong></div>
        `;
        document.querySelectorAll('.classification-btn').forEach(b => b.disabled = true);
    } catch (err) {
        resultEl.innerHTML = `<span class="error">Failed to submit: ${escapeHtml(err.message)}</span>`;
    }
}

// Attach classification handler to modal body (event delegation)
document.getElementById('modalBody').addEventListener('click', handleClassificationClick);

function closeModal() {
    document.getElementById('modal').classList.add('hidden');
}

// ---------- Utilities ----------

function formatTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleString();
}

function truncate(str, len) {
    if (!str) return '-';
    return str.length > len ? str.slice(0, len) + '…' : str;
}

function formatValue(v) {
    if (v === null || v === undefined) return '-';
    if (typeof v === 'object') return `<pre style="margin:0;white-space:pre-wrap;word-break:break-word;font-size:12px">${escapeHtml(JSON.stringify(v, null, 2))}</pre>`;
    return escapeHtml(String(v));
}

function escapeHtml(text) {
    if (text == null) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Start
init();

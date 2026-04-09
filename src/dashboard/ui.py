"""Single-page dashboard HTML/CSS/JS served inline by FastAPI."""

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Company Sourcing Agent</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
    --text: #e4e4e7; --muted: #8b8d97; --accent: #6366f1;
    --green: #22c55e; --red: #ef4444; --yellow: #eab308;
    --blue: #3b82f6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
    padding: 1.5rem; max-width: 1200px; margin: 0 auto;
  }
  h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 0.25rem; }
  .subtitle { color: var(--muted); font-size: 0.875rem; margin-bottom: 1.5rem; }

  /* Stats bar */
  .stats {
    display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;
  }
  .stat-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 1rem 1.25rem; min-width: 150px; flex: 1;
  }
  .stat-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }
  .stat-value { font-size: 1.5rem; font-weight: 700; margin-top: 0.25rem; }

  /* Controls */
  .controls {
    display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; align-items: center;
  }
  .controls select, .controls button {
    background: var(--surface); color: var(--text); border: 1px solid var(--border);
    border-radius: 6px; padding: 0.5rem 0.75rem; font-size: 0.875rem; cursor: pointer;
  }
  .controls button:hover { border-color: var(--accent); }
  .controls button.primary {
    background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600;
  }

  /* Company table */
  .table-wrap {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; overflow: hidden;
  }
  table { width: 100%; border-collapse: collapse; }
  th {
    text-align: left; font-size: 0.75rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.05em;
    padding: 0.75rem 1rem; border-bottom: 1px solid var(--border);
  }
  td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.875rem; }
  tr:last-child td { border-bottom: none; }
  tr:hover { background: rgba(99,102,241,0.05); cursor: pointer; }

  .score-badge {
    display: inline-block; padding: 0.125rem 0.5rem; border-radius: 9999px;
    font-weight: 600; font-size: 0.8rem;
  }
  .score-high { background: rgba(34,197,94,0.15); color: var(--green); }
  .score-med  { background: rgba(234,179,8,0.15); color: var(--yellow); }
  .score-low  { background: rgba(239,68,68,0.15); color: var(--red); }

  .trend-up { color: var(--green); }
  .trend-down { color: var(--red); }
  .trend-stable { color: var(--muted); }

  .signal-count {
    display: inline-flex; align-items: center; gap: 0.25rem;
    background: rgba(59,130,246,0.1); color: var(--blue);
    padding: 0.125rem 0.5rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 500;
  }

  /* Detail panel (modal) */
  .modal-overlay {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    z-index: 100; justify-content: center; align-items: flex-start;
    padding: 3rem 1rem; overflow-y: auto;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; width: 100%; max-width: 720px; padding: 1.5rem;
  }
  .modal-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    margin-bottom: 1rem;
  }
  .modal-header h2 { font-size: 1.25rem; }
  .modal-close {
    background: none; border: none; color: var(--muted); font-size: 1.5rem;
    cursor: pointer; line-height: 1;
  }
  .detail-scores {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 0.75rem; margin-bottom: 1.25rem;
  }
  .detail-score-card {
    background: var(--bg); border-radius: 8px; padding: 0.75rem; text-align: center;
  }
  .detail-score-card .label { font-size: 0.7rem; color: var(--muted); text-transform: uppercase; }
  .detail-score-card .value { font-size: 1.25rem; font-weight: 700; margin-top: 0.25rem; }

  .reasoning {
    background: var(--bg); border-radius: 8px; padding: 0.75rem 1rem;
    font-size: 0.85rem; color: var(--muted); margin-bottom: 1.25rem; line-height: 1.6;
  }

  .section-title {
    font-size: 0.8rem; color: var(--muted); text-transform: uppercase;
    letter-spacing: 0.05em; margin-bottom: 0.5rem; margin-top: 1rem;
  }

  .signal-item {
    background: var(--bg); border-radius: 8px; padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
  }
  .signal-item .sig-header {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;
  }
  .signal-type {
    font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
    padding: 0.125rem 0.5rem; border-radius: 4px;
    background: rgba(99,102,241,0.15); color: var(--accent);
  }
  .signal-date { font-size: 0.75rem; color: var(--muted); }
  .signal-title { font-size: 0.85rem; font-weight: 500; }
  .signal-content { font-size: 0.8rem; color: var(--muted); margin-top: 0.25rem; }
  .signal-link { color: var(--accent); font-size: 0.8rem; text-decoration: none; }
  .signal-link:hover { text-decoration: underline; }

  .meta-row { font-size: 0.8rem; color: var(--muted); margin-bottom: 0.25rem; }
  .meta-row span { color: var(--text); }

  .empty-state {
    text-align: center; padding: 3rem; color: var(--muted);
  }
  .loading { text-align: center; padding: 2rem; color: var(--muted); }
</style>
</head>
<body>

<h1>&#x1F50D; Company Sourcing Agent</h1>
<p class="subtitle">Companies ranked by investment potential — powered by signal aggregation</p>

<div class="stats" id="stats">
  <div class="stat-card"><div class="stat-label">Companies</div><div class="stat-value" id="stat-companies">—</div></div>
  <div class="stat-card"><div class="stat-label">Signals</div><div class="stat-value" id="stat-signals">—</div></div>
  <div class="stat-card"><div class="stat-label">Trending Up</div><div class="stat-value trend-up" id="stat-up">—</div></div>
  <div class="stat-card"><div class="stat-label">Trending Down</div><div class="stat-value trend-down" id="stat-down">—</div></div>
  <div class="stat-card"><div class="stat-label">Top Score</div><div class="stat-value" id="stat-top">—</div></div>
</div>

<div class="controls">
  <select id="sort-select">
    <option value="score">Sort by Score</option>
    <option value="signals">Sort by Signal Count</option>
    <option value="recent">Sort by Recent Activity</option>
    <option value="name">Sort by Name</option>
  </select>
  <select id="direction-select">
    <option value="all">All Trends</option>
    <option value="up">Trending Up</option>
    <option value="stable">Stable</option>
    <option value="down">Trending Down</option>
  </select>
  <button class="primary" onclick="refreshScores()">&#x21BB; Refresh Scores</button>
</div>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Company</th>
        <th>Score</th>
        <th>Signal Strength</th>
        <th>Momentum</th>
        <th>Signals</th>
        <th>Trend</th>
      </tr>
    </thead>
    <tbody id="company-table">
      <tr><td colspan="7" class="loading">Loading companies...</td></tr>
    </tbody>
  </table>
</div>

<!-- Detail Modal -->
<div class="modal-overlay" id="detail-modal">
  <div class="modal">
    <div class="modal-header">
      <h2 id="modal-name">Company</h2>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div id="modal-content"></div>
  </div>
</div>

<script>
const API = '';

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function scoreBadge(score) {
  const cls = score >= 60 ? 'score-high' : score >= 30 ? 'score-med' : 'score-low';
  return `<span class="score-badge ${cls}">${score.toFixed(1)}</span>`;
}

function trendIcon(dir) {
  if (dir === 'up') return '<span class="trend-up">&#x25B2; Up</span>';
  if (dir === 'down') return '<span class="trend-down">&#x25BC; Down</span>';
  return '<span class="trend-stable">&#x25CF; Stable</span>';
}

async function loadStats() {
  try {
    const s = await fetchJSON(API + '/api/stats');
    document.getElementById('stat-companies').textContent = s.total_companies;
    document.getElementById('stat-signals').textContent = s.total_signals;
    document.getElementById('stat-up').textContent = s.trending_up;
    document.getElementById('stat-down').textContent = s.trending_down;
    document.getElementById('stat-top').textContent = s.top_score.toFixed(1);
  } catch (e) {
    console.error('Failed to load stats', e);
  }
}

async function loadCompanies() {
  const sort = document.getElementById('sort-select').value;
  const dir = document.getElementById('direction-select').value;
  const tbody = document.getElementById('company-table');

  try {
    const companies = await fetchJSON(
      API + `/api/companies?limit=100&sort=${sort}&direction=${dir}`
    );

    if (companies.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No companies found. Run the HN or Twitter monitors to discover companies.</td></tr>';
      return;
    }

    tbody.innerHTML = companies.map((c, i) => `
      <tr onclick="openDetail('${c.id}')">
        <td>${i + 1}</td>
        <td><strong>${esc(c.name)}</strong></td>
        <td>${scoreBadge(c.overall_score)}</td>
        <td>${scoreBadge(c.signal_strength)}</td>
        <td>${scoreBadge(c.momentum)}</td>
        <td><span class="signal-count">${c.signal_count}</span></td>
        <td>${trendIcon(c.trending)}</td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state">Error loading companies: ${esc(e.message)}</td></tr>`;
  }
}

async function openDetail(id) {
  const modal = document.getElementById('detail-modal');
  const content = document.getElementById('modal-content');
  document.getElementById('modal-name').textContent = 'Loading...';
  content.innerHTML = '<div class="loading">Loading details...</div>';
  modal.classList.add('open');

  try {
    const c = await fetchJSON(API + `/api/companies/${id}`);
    document.getElementById('modal-name').textContent = c.name;

    let html = '';

    // Meta info
    html += '<div style="margin-bottom:1rem;">';
    if (c.domain) html += `<div class="meta-row">Domain: <span>${esc(c.domain)}</span></div>`;
    html += `<div class="meta-row">Source: <span>${esc(c.source)}</span></div>`;
    html += `<div class="meta-row">Status: <span>${esc(c.status)}</span></div>`;
    if (c.discovered_at) html += `<div class="meta-row">Discovered: <span>${new Date(c.discovered_at).toLocaleDateString()}</span></div>`;
    if (c.description) html += `<div class="meta-row" style="margin-top:0.5rem;">${esc(c.description)}</div>`;
    html += '</div>';

    // Score cards
    html += '<div class="detail-scores">';
    html += scoreCard('Overall', c.score.overall);
    html += scoreCard('Signal Str.', c.score.signal_strength);
    html += scoreCard('Momentum', c.score.momentum);
    html += scoreCard('Diversity', c.score.source_diversity);
    html += '</div>';

    // Trending
    html += `<div style="text-align:center;margin-bottom:1rem;">${trendIcon(c.score.trending)}</div>`;

    // Reasoning
    html += `<div class="reasoning">${esc(c.score.reasoning)}</div>`;

    // Signals timeline
    html += '<div class="section-title">Signals Timeline (' + c.signal_count + ')</div>';
    if (c.signals.length === 0) {
      html += '<div class="empty-state">No signals yet</div>';
    } else {
      for (const sig of c.signals) {
        html += `<div class="signal-item">
          <div class="sig-header">
            <span class="signal-type">${esc(sig.type)}</span>
            <span class="signal-date">${sig.created_at ? new Date(sig.created_at).toLocaleDateString() : '—'}</span>
          </div>
          <div class="signal-title">${esc(sig.title)}</div>
          ${sig.content ? `<div class="signal-content">${esc(sig.content).substring(0, 200)}</div>` : ''}
          ${sig.source_url ? `<a class="signal-link" href="${esc(sig.source_url)}" target="_blank">View source &#x2197;</a>` : ''}
        </div>`;
      }
    }

    // Score history
    if (c.score_history && c.score_history.length > 0) {
      html += '<div class="section-title">Score History</div>';
      for (const sh of c.score_history) {
        html += `<div class="signal-item">
          <div class="sig-header">
            <span class="score-badge ${sh.overall >= 60 ? 'score-high' : sh.overall >= 30 ? 'score-med' : 'score-low'}">${sh.overall.toFixed(1)}</span>
            <span class="signal-date">${sh.created_at ? new Date(sh.created_at).toLocaleDateString() : '—'} · ${esc(sh.scored_by)}</span>
          </div>
        </div>`;
      }
    }

    content.innerHTML = html;
  } catch (e) {
    content.innerHTML = `<div class="empty-state">Error: ${esc(e.message)}</div>`;
  }
}

function closeModal() {
  document.getElementById('detail-modal').classList.remove('open');
}

function scoreCard(label, value) {
  const cls = value >= 60 ? 'trend-up' : value >= 30 ? '' : 'trend-down';
  return `<div class="detail-score-card"><div class="label">${label}</div><div class="value ${cls}">${value.toFixed(1)}</div></div>`;
}

async function refreshScores() {
  try {
    await fetch(API + '/api/score/refresh', { method: 'POST' });
    loadStats();
    loadCompanies();
  } catch (e) {
    alert('Failed to refresh scores: ' + e.message);
  }
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Close modal on overlay click
document.getElementById('detail-modal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});

// Reload on filter change
document.getElementById('sort-select').addEventListener('change', loadCompanies);
document.getElementById('direction-select').addEventListener('change', loadCompanies);

// Initial load
loadStats();
loadCompanies();
</script>
</body>
</html>
"""

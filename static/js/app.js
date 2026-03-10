/**
 * F1InsightAI — Formula 1 Data Chatbot
 * Server-side conversations + Agent step display
 */

// ── DOM Elements ────────────────────────────────────────────
const chatArea = document.getElementById('chatArea');
const chatForm = document.getElementById('chatForm');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const welcomeCard = document.getElementById('welcomeCard');
const toastContainer = document.getElementById('toastContainer');

// Sidebar
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarCollapse = document.getElementById('sidebarCollapse');
const chatList = document.getElementById('chatList');
const newChatBtn = document.getElementById('newChatBtn');
const clearAllChats = document.getElementById('clearAllChats');

// Theme
const themeToggle = document.getElementById('themeToggle');

// Stats
const statTables = document.getElementById('statTables');
const statRows = document.getElementById('statRows');
const statColumns = document.getElementById('statColumns');
const statModel = document.getElementById('statModel');


// Store the initial welcome card HTML so we can restore it
const welcomeCardHTML = welcomeCard ? welcomeCard.outerHTML : '';


// ── State ───────────────────────────────────────────────────
let isLoading = false;
let currentChatId = null;
let conversations = []; // Loaded from server
let sidebarCollapsed = false;


// ── Initialize ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    loadStats();
    loadTheme();
    loadConversations();
    autoResizeTextarea();

    // Restore collapsed state from localStorage
    const savedCollapsed = localStorage.getItem('f1_sidebar_collapsed');
    if (savedCollapsed === 'true' && window.innerWidth > 768) {
        collapseSidebar();
    }
});


// ── Health Check ────────────────────────────────────────────
async function checkHealth() {
    try {
        const res = await fetch('/api/health');
        const data = await res.json();
        if (data.status === 'healthy') {
            statusDot.className = 'status-dot online';
            statusText.textContent = `${data.rag_indexed ? data.model : 'Connecting...'}`;
        } else {
            statusDot.className = 'status-dot error';
            statusText.textContent = 'DB disconnected';
        }
    } catch {
        statusDot.className = 'status-dot error';
        statusText.textContent = 'Offline';
    }
}


// ── Load Database Stats ─────────────────────────────────────
async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        statTables.textContent = data.table_count;
        statRows.textContent = data.total_rows.toLocaleString();
        statColumns.textContent = data.total_columns;
        statModel.textContent = data.model.split('-').slice(0, 2).join(' ');
    } catch {
        // Stats failed, leave placeholders
    }
}


// ── Theme Toggle ────────────────────────────────────────────
function loadTheme() {
    const saved = localStorage.getItem('nw_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
}

themeToggle.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('nw_theme', next);
    showToast(`Switched to ${next} mode`, 'info');
});


// ── Sidebar Collapse / Expand ───────────────────────────────
function collapseSidebar() {
    sidebarCollapsed = true;
    sidebar.classList.add('collapsed');
    document.querySelector('.app-container').classList.add('sidebar-collapsed');
    sidebarToggle.style.display = 'flex';
    localStorage.setItem('f1_sidebar_collapsed', 'true');
}

function expandSidebar() {
    sidebarCollapsed = false;
    sidebar.classList.remove('collapsed');
    document.querySelector('.app-container').classList.remove('sidebar-collapsed');
    if (window.innerWidth > 768) {
        sidebarToggle.style.display = 'none';
    }
    localStorage.setItem('f1_sidebar_collapsed', 'false');
}

// Collapse button inside sidebar
sidebarCollapse.addEventListener('click', () => {
    if (window.innerWidth <= 768) {
        // Mobile: close overlay
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('open');
    } else {
        // Desktop: collapse
        collapseSidebar();
    }
});

// Toggle button in header (expands collapsed sidebar)
sidebarToggle.addEventListener('click', () => {
    if (window.innerWidth <= 768) {
        sidebar.classList.add('open');
        sidebarOverlay.classList.add('open');
    } else {
        expandSidebar();
    }
});

sidebarOverlay.addEventListener('click', () => {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('open');
});


// ── Conversation Management (Server-Side) ───────────────────

async function loadConversations() {
    try {
        const res = await fetch('/api/conversations');
        const data = await res.json();
        conversations = data.conversations || [];
        renderChatList();
    } catch {
        conversations = [];
        renderChatList();
    }
}

// Create a new chat
newChatBtn.addEventListener('click', () => {
    startNewChat();
    if (window.innerWidth <= 768) {
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('open');
    }
});

function startNewChat() {
    currentChatId = null;
    chatArea.innerHTML = welcomeCardHTML;
    renderChatList();
    loadStats();  // Re-populate stat cards
    userInput.focus();
}

// Clear all chats
clearAllChats.addEventListener('click', async () => {
    if (conversations.length === 0) return;
    try {
        await fetch('/api/conversations/clear', { method: 'DELETE' });
        conversations = [];
        startNewChat();
        showToast('All chats cleared', 'info');
    } catch {
        showToast('Failed to clear chats', 'error');
    }
});

// Load a specific conversation
async function loadChat(chatId) {
    currentChatId = chatId;
    chatArea.innerHTML = '';

    try {
        const res = await fetch(`/api/conversations/${chatId}`);
        const data = await res.json();
        const messages = data.messages || [];

        messages.forEach(msg => {
            if (msg.role === 'user') {
                appendMessageDOM('user', msg.content);
            } else if (msg.role === 'assistant') {
                if (msg.data) {
                    appendAssistantMessageDOM(msg.data);
                } else {
                    appendMessageDOM('assistant', msg.content);
                }
            } else if (msg.role === 'error') {
                appendErrorDOM(msg.content, '');
            }
        });

        renderChatList();
        scrollToBottom();
    } catch {
        showToast('Failed to load chat', 'error');
    }
}

async function deleteChat(chatId, event) {
    event.stopPropagation();
    try {
        await fetch(`/api/conversations/${chatId}`, { method: 'DELETE' });
        conversations = conversations.filter(c => c.id !== chatId);
        startNewChat();  // Always go to a fresh new chat
        showToast('Chat deleted', 'info');
    } catch {
        showToast('Failed to delete chat', 'error');
    }
}

async function renameChat(chatId, event) {
    event.stopPropagation();
    const chat = conversations.find(c => c.id === chatId);
    if (!chat) return;

    const item = event.target.closest('.chat-item');
    const titleEl = item.querySelector('.chat-item-title');
    const oldTitle = chat.title;

    // Replace title with input
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'chat-rename-input';
    input.value = oldTitle;
    titleEl.replaceWith(input);
    input.focus();
    input.select();

    const save = async () => {
        const newTitle = input.value.trim();
        if (newTitle && newTitle !== oldTitle) {
            try {
                await fetch(`/api/conversations/${chatId}/rename`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: newTitle })
                });
                chat.title = newTitle;
                showToast('Chat renamed', 'info');
            } catch {
                showToast('Rename failed', 'error');
            }
        }
        renderChatList();
    };

    input.addEventListener('blur', save);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
        if (e.key === 'Escape') { input.value = oldTitle; input.blur(); }
    });
}

async function pinChat(chatId, event) {
    event.stopPropagation();
    const chat = conversations.find(c => c.id === chatId);
    if (!chat) return;

    const newPinned = !chat.pinned;
    try {
        await fetch(`/api/conversations/${chatId}/pin`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pinned: newPinned })
        });
        chat.pinned = newPinned;
        // Re-sort: pinned first, then by updated_at
        conversations.sort((a, b) => {
            if (a.pinned !== b.pinned) return b.pinned ? 1 : -1;
            return new Date(b.updated_at) - new Date(a.updated_at);
        });
        renderChatList();
        showToast(newPinned ? 'Chat pinned' : 'Chat unpinned', 'info');
    } catch {
        showToast('Pin failed', 'error');
    }
}

// Render the conversation list in sidebar
function renderChatList() {
    if (conversations.length === 0) {
        chatList.innerHTML = `
            <div class="sidebar-empty">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
                <p>No conversations yet</p>
            </div>`;
        return;
    }

    const today = new Date().toDateString();
    const yesterday = new Date(Date.now() - 86400000).toDateString();

    let html = '';
    let lastDateLabel = '';
    let hasPinned = conversations.some(c => c.pinned);
    let pinnedSectionDone = false;

    conversations.forEach(chat => {
        // Add PINNED section header
        if (chat.pinned && !pinnedSectionDone && lastDateLabel === '') {
            html += `<div class="sidebar-date-label">📌 Pinned</div>`;
        }
        // Transition from pinned to unpinned
        if (!chat.pinned && !pinnedSectionDone && hasPinned) {
            pinnedSectionDone = true;
            lastDateLabel = ''; // Reset so date labels show
        }

        if (!chat.pinned) {
            const chatDate = new Date(chat.created_at || chat.createdAt).toDateString();
            let dateLabel;
            if (chatDate === today) dateLabel = 'Today';
            else if (chatDate === yesterday) dateLabel = 'Yesterday';
            else dateLabel = new Date(chat.created_at || chat.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

            if (dateLabel !== lastDateLabel) {
                html += `<div class="sidebar-date-label">${dateLabel}</div>`;
                lastDateLabel = dateLabel;
            }
        }

        const isActive = chat.id === currentChatId;
        const pinIcon = chat.pinned ? '📌 ' : '';
        const pinTitle = chat.pinned ? 'Unpin' : 'Pin';
        const pinSvg = chat.pinned
            ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M16 2L7.5 10.5 2 22l11.5-5.5L22 8 16 2z"/></svg>'
            : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 2L7.5 10.5 2 22l11.5-5.5L22 8 16 2z"/></svg>';

        html += `
            <div class="chat-item${isActive ? ' active' : ''}${chat.pinned ? ' pinned' : ''}" onclick="loadChat('${chat.id}')">
                <div class="chat-item-content">
                    <div class="chat-item-title">${pinIcon}${escapeHtml(chat.title)}</div>
                </div>
                <div class="chat-item-actions">
                    <button class="chat-item-action" onclick="pinChat('${chat.id}', event)" title="${pinTitle}">
                        ${pinSvg}
                    </button>
                    <button class="chat-item-action" onclick="renameChat('${chat.id}', event)" title="Rename">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                        </svg>
                    </button>
                    <button class="chat-item-action delete" onclick="deleteChat('${chat.id}', event)" title="Delete">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
            </div>`;
    });

    chatList.innerHTML = html;
}


// ── Form Handling ───────────────────────────────────────────
chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const msg = userInput.value.trim();
    if (msg && !isLoading) {
        sendMessage(msg);
    }
});

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

function autoResizeTextarea() {
    userInput.addEventListener('input', () => {
        userInput.style.height = 'auto';
        userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
    });
}

// Global function for suggestion chips
function askQuestion(text) {
    if (!isLoading) {
        userInput.value = text;
        sendMessage(text);
    }
}


// ── Send Message ────────────────────────────────────────────
async function sendMessage(message) {
    isLoading = true;
    sendBtn.disabled = true;

    // Hide welcome card if visible
    const wc = document.getElementById('welcomeCard');
    if (wc) wc.remove();

    // Add user message to DOM
    appendMessageDOM('user', message);

    userInput.value = '';
    userInput.style.height = 'auto';

    // Show typing indicator
    const typingEl = appendTyping();

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                conversation_id: currentChatId,
            }),
        });

        const data = await res.json();
        removeTyping(typingEl);

        // Update current chat ID (server may have created a new one)
        if (data.conversation_id) {
            currentChatId = data.conversation_id;
        }

        // Refresh conversation list from server
        await loadConversations();

        if (data.error && !data.answer) {
            appendErrorDOM(data.error, message);
        } else {
            appendAssistantMessageDOM(data);
        }
    } catch (err) {
        removeTyping(typingEl);
        appendErrorDOM('Failed to connect to the server. Please check if the app is running.', message);
    }

    isLoading = false;
    sendBtn.disabled = false;
    userInput.focus();
}


// ── DOM Rendering ───────────────────────────────────────────
function appendMessageDOM(role, text) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    const avatar = role === 'user' ? 'You' : 'AI';
    div.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            <div class="message-bubble">${escapeHtml(text)}</div>
        </div>`;
    chatArea.appendChild(div);
    scrollToBottom();
}

function appendAssistantMessageDOM(data) {
    const div = document.createElement('div');
    div.className = 'message assistant';

    let html = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <div class="message-bubble">${escapeHtml(data.answer || 'No answer generated.')}</div>`;

    // Execution time badge
    if (data.execution_time) {
        html += `
            <div class="exec-stats">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                </svg>
                ${data.execution_time}s
            </div>`;
    }

    // Agent steps (reasoning trace)
    if (data.agent_steps && data.agent_steps.length > 0) {
        html += `
            <details class="agent-steps">
                <summary>🧠 Agent Reasoning (${data.agent_steps.length} steps)</summary>
                <div class="agent-steps-list">`;
        data.agent_steps.forEach((step, i) => {
            const icon = step.result && step.result.startsWith('✅') ? '✅' :
                step.result && step.result.startsWith('❌') ? '❌' :
                    step.result && step.result.startsWith('⚠️') ? '⚠️' : '🔧';
            html += `
                    <div class="agent-step">
                        <span class="agent-step-num">${i + 1}</span>
                        <div class="agent-step-content">
                            <div class="agent-step-node">${escapeHtml(step.node || '')}</div>
                            <div class="agent-step-action">${escapeHtml(step.action || '')}</div>
                            <div class="agent-step-result">${escapeHtml(step.result || '')}</div>
                        </div>
                    </div>`;
        });
        html += `</div></details>`;
    }

    // SQL block
    if (data.sql) {
        html += `
            <div class="sql-block">
                <div class="sql-header">
                    <span>Generated SQL</span>
                    <div class="sql-actions">
                        <button class="copy-btn" onclick="copySQL(this, \`${escapeForTemplate(data.sql)}\`)">Copy</button>
                        <button class="copy-btn" onclick="downloadSQL(\`${escapeForTemplate(data.sql)}\`)">↓ .sql</button>
                    </div>
                </div>
                <pre class="sql-code">${highlightSQL(data.sql)}</pre>
            </div>`;
    }

    // Results table + chart
    const chartId = 'chart_' + Date.now();
    if (data.results && data.results.rows && data.results.rows.length > 0) {
        const cols = data.results.columns;
        const rows = data.results.rows;
        const tableId = 'table_' + Date.now();

        html += `
            <div class="results-block">
                <div class="results-header">
                    <div class="results-header-left">
                        <span>Query Results</span>
                        <span class="results-count">${data.results.row_count} row${data.results.row_count > 1 ? 's' : ''}</span>
                    </div>
                    <button class="csv-btn" onclick="downloadCSV('${tableId}')">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                            <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                        </svg>
                        CSV
                    </button>
                </div>
                <div class="results-table-container">
                    <table class="results-table" id="${tableId}">
                        <thead><tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>
                        <tbody>
                            ${rows.map(row =>
            `<tr>${cols.map(c => `<td title="${escapeHtml(String(row[c] ?? ''))}">${escapeHtml(String(row[c] ?? 'NULL'))}</td>`).join('')}</tr>`
        ).join('')}
                        </tbody>
                    </table>
                </div>
            </div>`;

        // Chart container
        const chartType = detectChartType(cols, rows);
        if (chartType) {
            html += `
                <div class="chart-block">
                    <div class="chart-header">
                        <span>📊 Visualization</span>
                    </div>
                    <div class="chart-container">
                        <canvas id="${chartId}"></canvas>
                    </div>
                </div>`;
        }
    }

    // Error from SQL execution
    if (data.error) {
        html += `
            <div class="error-text">
                <span>⚠️ ${escapeHtml(data.error)}</span>
                <button class="retry-btn" onclick="askQuestion('${escapeForTemplate(data.answer ? '' : 'Retry: ' + data.error)}')"> Retry</button>
            </div>`;
    }

    // Follow-up suggestions
    if (data.follow_ups && data.follow_ups.length > 0) {
        html += `<div class="follow-ups">`;
        data.follow_ups.forEach(q => {
            html += `<button class="follow-up-chip" onclick="askQuestion('${escapeForTemplate(q)}')">${escapeHtml(q)}</button>`;
        });
        html += `</div>`;
    }

    html += '</div>';
    div.innerHTML = html;
    chatArea.appendChild(div);
    scrollToBottom();

    // Render chart AFTER DOM insertion
    if (data.results && data.results.rows && data.results.rows.length > 0) {
        const chartCanvas = document.getElementById(chartId);
        if (chartCanvas) {
            renderChart(chartCanvas, data.results.columns, data.results.rows);
        }
    }
}

function appendErrorDOM(error, originalQuestion) {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <div class="error-text">
                <span>⚠️ ${escapeHtml(error)}</span>
                <button class="retry-btn" onclick="askQuestion('${escapeForTemplate(originalQuestion)}')">Retry</button>
            </div>
        </div>`;
    chatArea.appendChild(div);
    scrollToBottom();
}

function appendTyping() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.id = 'typing-msg';
    div.innerHTML = `
        <div class="message-avatar">AI</div>
        <div class="message-content">
            <div class="message-bubble">
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        </div>`;
    chatArea.appendChild(div);
    scrollToBottom();
    return div;
}

function removeTyping(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
}


// ── CSV Export ──────────────────────────────────────────────
function downloadCSV(tableId) {
    const table = document.getElementById(tableId);
    if (!table) return;

    let csv = [];
    const rows = table.querySelectorAll('tr');
    rows.forEach(row => {
        const cells = row.querySelectorAll('th, td');
        const rowData = Array.from(cells).map(cell => {
            let text = cell.textContent.replace(/"/g, '""');
            return `"${text}"`;
        });
        csv.push(rowData.join(','));
    });

    const blob = new Blob([csv.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `f1_results_${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    showToast('CSV downloaded!', 'success');
}


// ── Copy SQL ────────────────────────────────────────────────
function copySQL(btn, sql) {
    navigator.clipboard.writeText(sql).then(() => {
        btn.textContent = '✓ Copied';
        setTimeout(() => btn.textContent = 'Copy', 2000);
        showToast('SQL copied to clipboard', 'success');
    }).catch(() => {
        showToast('Failed to copy', 'error');
    });
}


// ── Download SQL ────────────────────────────────────────────
function downloadSQL(sql) {
    const blob = new Blob([sql], { type: 'application/sql;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `f1_query_${Date.now()}.sql`;
    link.click();
    URL.revokeObjectURL(url);
    showToast('SQL file downloaded!', 'success');
}


// ── Toast Notifications ─────────────────────────────────────
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: '✓',
        error: '✕',
        info: 'ℹ',
    };

    toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span> ${escapeHtml(message)}`;
    toastContainer.appendChild(toast);

    setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 3000);
}


// ── SQL Syntax Highlighting ─────────────────────────────────
function highlightSQL(sql) {
    const escaped = escapeHtml(sql);
    const keywords = [
        'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN',
        'INNER JOIN', 'OUTER JOIN', 'ON', 'AS', 'AND', 'OR', 'NOT',
        'IN', 'LIKE', 'BETWEEN', 'IS', 'NULL', 'GROUP BY', 'ORDER BY',
        'HAVING', 'LIMIT', 'OFFSET', 'UNION', 'DISTINCT', 'CASE',
        'WHEN', 'THEN', 'ELSE', 'END', 'DESC', 'ASC', 'WITH', 'EXISTS',
    ];

    let result = escaped;

    keywords.forEach(kw => {
        const regex = new RegExp(`\\b(${kw})\\b`, 'gi');
        result = result.replace(regex, '<span class="sql-keyword">$1</span>');
    });

    const functions = ['COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'CONCAT', 'COALESCE', 'IFNULL', 'ROUND', 'CAST', 'DATE', 'YEAR', 'MONTH'];
    functions.forEach(fn => {
        const regex = new RegExp(`\\b(${fn})\\s*\\(`, 'gi');
        result = result.replace(regex, '<span class="sql-function">$1</span>(');
    });

    result = result.replace(/\b(\d+\.?\d*)\b/g, '<span class="sql-number">$1</span>');
    result = result.replace(/&#39;([^&#]*?)&#39;/g, '<span class="sql-string">\'$1\'</span>');

    return result;
}


// ── Chart.js Auto-Visualization ─────────────────────────────
const CHART_COLORS = [
    '#6C63FF', '#00D2FF', '#FF6B6B', '#FFD93D', '#6BCB77',
    '#4D96FF', '#FF6F91', '#845EC2', '#FF9671', '#FFC75F',
];

function detectChartType(columns, rows) {
    if (!rows || rows.length === 0 || rows.length > 50) return null;
    if (columns.length < 2) return null;

    const textCols = [];
    const numCols = [];

    columns.forEach(col => {
        const values = rows.map(r => r[col]).filter(v => v !== null && v !== undefined);
        const numericCount = values.filter(v => !isNaN(Number(v)) && v !== '').length;
        if (numericCount > values.length * 0.7) {
            numCols.push(col);
        } else {
            textCols.push(col);
        }
    });

    if (textCols.length === 0 || numCols.length === 0) return null;

    const firstTextCol = textCols[0];
    const firstVal = String(rows[0][firstTextCol] || '');
    const isDateLike = /\d{4}[-/]\d{1,2}|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|q[1-4])\b/i.test(firstVal)
        || /^\d{4}$/.test(firstVal);

    if (isDateLike) return 'line';
    if (rows.length <= 8 && numCols.length === 1) return 'pie';
    return 'bar';
}

function renderChart(canvas, columns, rows) {
    const chartType = detectChartType(columns, rows);
    if (!chartType) return;

    const textCols = [];
    const numCols = [];

    columns.forEach(col => {
        const values = rows.map(r => r[col]).filter(v => v !== null && v !== undefined);
        const numericCount = values.filter(v => !isNaN(Number(v)) && v !== '').length;
        if (numericCount > values.length * 0.7) numCols.push(col);
        else textCols.push(col);
    });

    const labels = rows.map(r => String(r[textCols[0]] ?? ''));
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = isDark ? '#a0a0b8' : '#555';
    const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.08)';

    const datasets = numCols.map((col, i) => {
        const data = rows.map(r => Number(r[col]) || 0);
        return {
            label: col.replace(/_/g, ' '),
            data: data,
            backgroundColor: chartType === 'pie'
                ? CHART_COLORS.slice(0, data.length)
                : CHART_COLORS[i % CHART_COLORS.length] + '99',
            borderColor: chartType === 'pie'
                ? '#1a1a2e'
                : CHART_COLORS[i % CHART_COLORS.length],
            borderWidth: 2,
            borderRadius: chartType === 'bar' ? 6 : 0,
            tension: 0.4,
            fill: chartType === 'line',
        };
    });

    new Chart(canvas, {
        type: chartType,
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: numCols.length > 1 || chartType === 'pie',
                    labels: { color: textColor, font: { family: 'Inter', size: 11 } },
                },
                tooltip: {
                    backgroundColor: isDark ? '#1e1e3a' : '#fff',
                    titleColor: isDark ? '#e0e0f0' : '#333',
                    bodyColor: isDark ? '#a0a0b8' : '#555',
                    borderColor: isDark ? 'rgba(108,99,255,0.3)' : '#ddd',
                    borderWidth: 1,
                    cornerRadius: 8,
                    padding: 10,
                },
            },
            scales: chartType !== 'pie' ? {
                x: {
                    ticks: { color: textColor, font: { size: 10 }, maxRotation: 45 },
                    grid: { color: gridColor },
                },
                y: {
                    ticks: { color: textColor, font: { size: 10 } },
                    grid: { color: gridColor },
                    beginAtZero: true,
                },
            } : {},
        },
    });
}


// ── Utilities ───────────────────────────────────────────────
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeForTemplate(text) {
    return text.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/'/g, "\\'").replace(/\n/g, '\\n');
}

function scrollToBottom() {
    setTimeout(() => {
        chatArea.scrollTop = chatArea.scrollHeight;
    }, 50);
}

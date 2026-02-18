/**
 * NorthwindAI — Text-to-SQL RAG Chatbot
 * ChatGPT-style conversation management with full history
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
const sidebarClose = document.getElementById('sidebarClose');
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
// conversations: { id, title, createdAt, messages: [{role, content, data?}] }
let conversations = JSON.parse(localStorage.getItem('nw_conversations') || '[]');


// ── Initialize ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    loadStats();
    loadTheme();
    renderChatList();
    autoResizeTextarea();
    // Always start fresh — users can load past chats from the sidebar
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


// ── Sidebar ─────────────────────────────────────────────────
sidebarToggle.addEventListener('click', () => {
    sidebar.classList.add('open');
    sidebarOverlay.classList.add('open');
});

sidebarClose.addEventListener('click', closeSidebar);
sidebarOverlay.addEventListener('click', closeSidebar);

function closeSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('open');
}


// ── Conversation Management (ChatGPT-style) ────────────────

function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
}

function saveConversations() {
    localStorage.setItem('nw_conversations', JSON.stringify(conversations));
}

// Create a new chat
newChatBtn.addEventListener('click', () => {
    startNewChat();
    closeSidebar();
});

function startNewChat() {
    currentChatId = null;
    // Clear chat area and show welcome card
    chatArea.innerHTML = welcomeCardHTML;
    renderChatList();
    userInput.focus();
}

// Clear all chats
clearAllChats.addEventListener('click', () => {
    if (conversations.length === 0) return;
    conversations = [];
    saveConversations();
    startNewChat();
    showToast('All chats cleared', 'info');
});

// Load a specific conversation
function loadChat(chatId) {
    const chat = conversations.find(c => c.id === chatId);
    if (!chat) return;

    currentChatId = chatId;

    // Clear chat area (remove welcome card)
    chatArea.innerHTML = '';

    // Re-render all messages from this conversation
    chat.messages.forEach(msg => {
        if (msg.role === 'user') {
            appendMessageDOM('user', msg.content);
        } else if (msg.role === 'assistant') {
            if (msg.data) {
                appendAssistantMessageDOM(msg.data);
            } else {
                appendMessageDOM('assistant', msg.content);
            }
        } else if (msg.role === 'error') {
            appendErrorDOM(msg.content, msg.originalQuestion || '');
        }
    });

    renderChatList();
    scrollToBottom();
}

// Delete a chat
function deleteChat(chatId, event) {
    event.stopPropagation();
    conversations = conversations.filter(c => c.id !== chatId);
    saveConversations();

    if (currentChatId === chatId) {
        if (conversations.length > 0) {
            loadChat(conversations[0].id);
        } else {
            startNewChat();
        }
    } else {
        renderChatList();
    }
    showToast('Chat deleted', 'info');
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

    // Group by date
    const today = new Date().toDateString();
    const yesterday = new Date(Date.now() - 86400000).toDateString();

    let html = '';
    let lastDateLabel = '';

    conversations.forEach(chat => {
        const chatDate = new Date(chat.createdAt).toDateString();
        let dateLabel;
        if (chatDate === today) dateLabel = 'Today';
        else if (chatDate === yesterday) dateLabel = 'Yesterday';
        else dateLabel = new Date(chat.createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        if (dateLabel !== lastDateLabel) {
            html += `<div class="sidebar-date-label">${dateLabel}</div>`;
            lastDateLabel = dateLabel;
        }

        const isActive = chat.id === currentChatId;
        html += `
            <div class="chat-item${isActive ? ' active' : ''}" onclick="loadChat('${chat.id}'); closeSidebar();">
                <div class="chat-item-content">
                    <div class="chat-item-title">${escapeHtml(chat.title)}</div>
                    <div class="chat-item-time">${new Date(chat.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                </div>
                <button class="chat-item-delete" onclick="deleteChat('${chat.id}', event)" title="Delete">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
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

    // If no active chat, create a new one
    if (!currentChatId) {
        const newChat = {
            id: generateId(),
            title: message.length > 50 ? message.substring(0, 50) + '...' : message,
            createdAt: new Date().toISOString(),
            messages: [],
        };
        conversations.unshift(newChat);
        currentChatId = newChat.id;
        saveConversations();
        renderChatList();
    }

    // Hide welcome card if visible
    const wc = document.getElementById('welcomeCard');
    if (wc) wc.remove();

    // Add user message to DOM and conversation
    appendMessageDOM('user', message);
    addMessageToChat(currentChatId, { role: 'user', content: message });

    userInput.value = '';
    userInput.style.height = 'auto';

    // Show typing indicator
    const typingEl = appendTyping();

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });

        const data = await res.json();
        removeTyping(typingEl);

        if (data.error && !data.answer) {
            appendErrorDOM(data.error, message);
            addMessageToChat(currentChatId, { role: 'error', content: data.error, originalQuestion: message });
        } else {
            appendAssistantMessageDOM(data);
            addMessageToChat(currentChatId, { role: 'assistant', content: data.answer || '', data: data });
        }
    } catch (err) {
        removeTyping(typingEl);
        const errMsg = 'Failed to connect to the server. Please check if the app is running.';
        appendErrorDOM(errMsg, message);
        addMessageToChat(currentChatId, { role: 'error', content: errMsg, originalQuestion: message });
    }

    isLoading = false;
    sendBtn.disabled = false;
    userInput.focus();
}

function addMessageToChat(chatId, message) {
    const chat = conversations.find(c => c.id === chatId);
    if (chat) {
        chat.messages.push(message);
        saveConversations();
    }
}


// ── DOM Rendering (pure display, no state changes) ──────────
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

    // Results table
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
    }

    // Error from SQL execution
    if (data.error) {
        html += `
            <div class="error-text">
                <span>⚠️ ${escapeHtml(data.error)}</span>
                <button class="retry-btn" onclick="askQuestion('${escapeForTemplate(data.answer ? '' : 'Retry: ' + data.error)}')">Retry</button>
            </div>`;
    }

    html += '</div>';
    div.innerHTML = html;
    chatArea.appendChild(div);
    scrollToBottom();
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
    link.download = `northwind_results_${Date.now()}.csv`;
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
    link.download = `northwind_query_${Date.now()}.sql`;
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

    // Highlight keywords
    keywords.forEach(kw => {
        const regex = new RegExp(`\\b(${kw})\\b`, 'gi');
        result = result.replace(regex, '<span class="sql-keyword">$1</span>');
    });

    // Highlight functions
    const functions = ['COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'CONCAT', 'COALESCE', 'IFNULL', 'ROUND', 'CAST', 'DATE', 'YEAR', 'MONTH'];
    functions.forEach(fn => {
        const regex = new RegExp(`\\b(${fn})\\s*\\(`, 'gi');
        result = result.replace(regex, '<span class="sql-function">$1</span>(');
    });

    // Highlight numbers
    result = result.replace(/\b(\d+\.?\d*)\b/g, '<span class="sql-number">$1</span>');

    // Highlight strings
    result = result.replace(/&#39;([^&#]*?)&#39;/g, '<span class="sql-string">\'$1\'</span>');

    return result;
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

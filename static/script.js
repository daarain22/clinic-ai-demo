/* ============================================================
   CarePlus AI Receptionist — Script
   ============================================================ */

const chatWindow  = document.getElementById('chatWindow');
const userInput   = document.getElementById('userInput');
const sendBtn     = document.getElementById('sendBtn');
const quickActions = document.getElementById('quickActions');

const SESSION_ID = 'sess_' + Math.random().toString(36).slice(2, 10);

/* ── Init ── */
(function init() {
  const chip = document.getElementById('dateChip');
  chip.setAttribute('data-date', 'Today, ' + new Date().toLocaleDateString('en-IN', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  }));
  document.getElementById('welcomeTime').textContent = timeStr();
  userInput.focus();
})();

/* ── Utilities ── */
function timeStr() {
  return new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
}

function scrollBottom() {
  chatWindow.scrollTo({ top: chatWindow.scrollHeight, behavior: 'smooth' });
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

/* ── Markdown renderer ── */
function renderMd(text) {
  let s = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Bold
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Horizontal rules
  s = s.replace(/─{3,}/g, '<hr>');

  const lines = s.split('\n');
  let html = '';
  let inUl = false;

  for (const line of lines) {
    const t = line.trim();
    if (!t) {
      if (inUl) { html += '</ul>'; inUl = false; }
      continue;
    }
    if (/^[-•]\s+/.test(t)) {
      if (!inUl) { html += '<ul>'; inUl = true; }
      html += `<li>${t.replace(/^[-•]\s+/, '')}</li>`;
    } else {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<p>${line}</p>`;
    }
  }
  if (inUl) html += '</ul>';
  return html;
}

/* ── Append message ── */
function appendMsg(text, role) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role === 'user' ? 'user-message' : 'bot-message'}`;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = renderMd(text);

  const time = document.createElement('span');
  time.className = 'msg-time';
  time.textContent = timeStr();
  bubble.appendChild(time);

  wrapper.appendChild(bubble);
  chatWindow.appendChild(wrapper);
  scrollBottom();
}

/* ── Typing indicator ── */
function showTyping() {
  const wrapper = document.createElement('div');
  wrapper.className = 'message bot-message';
  wrapper.id = 'typingRow';

  const ind = document.createElement('div');
  ind.className = 'typing-indicator';
  ind.innerHTML = '<span></span><span></span><span></span>';

  wrapper.appendChild(ind);
  chatWindow.appendChild(wrapper);
  scrollBottom();
}

function hideTyping() {
  const el = document.getElementById('typingRow');
  if (el) el.remove();
}

/* ── Send message ── */
async function sendMessage(override = null) {
  const text = (override ?? userInput.value).trim();
  if (!text) return;

  quickActions.style.display = 'none';

  userInput.value = '';
  userInput.style.height = 'auto';
  sendBtn.disabled = true;
  userInput.disabled = true;

  appendMsg(text, 'user');
  showTyping();

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: SESSION_ID }),
    });

    hideTyping();

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      appendMsg('⚠️ ' + (err.detail || 'Something went wrong. Please try again.'), 'bot');
    } else {
      const data = await res.json();
      appendMsg(data.response, 'bot');
    }
  } catch {
    hideTyping();
    appendMsg('⚠️ Connection error. Please check your network and try again.', 'bot');
  } finally {
    sendBtn.disabled = false;
    userInput.disabled = false;
    userInput.focus();
  }
}

function sendQuick(text) { sendMessage(text); }

/* ── Reset ── */
async function resetChat() {
  try { await fetch(`/chat/reset?session_id=${SESSION_ID}`, { method: 'DELETE' }); } catch {}

  chatWindow.innerHTML = '';

  const chip = document.createElement('div');
  chip.className = 'date-chip';
  chip.id = 'dateChip';
  chip.setAttribute('data-date', 'Today, ' + new Date().toLocaleDateString('en-IN', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
  }));
  chatWindow.appendChild(chip);

  const welcome = document.createElement('div');
  welcome.className = 'message bot-message';
  welcome.innerHTML = `
    <div class="bubble">
      <p>👋 Welcome to <strong>CarePlus Multispeciality Clinic</strong>, Mysore!</p>
      <p>I'm Aria, your AI receptionist. I can help you with doctor information, clinic timings, consultation fees, location, and booking appointments.</p>
      <p>How may I assist you today?</p>
      <span class="msg-time">${timeStr()}</span>
    </div>`;
  chatWindow.appendChild(welcome);

  quickActions.style.display = 'flex';
  userInput.focus();
}

/* ── Key handler ── */
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

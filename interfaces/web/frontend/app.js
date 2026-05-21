(function() {

const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${wsProto}//${location.host}/ws/chat`;

let ws = null;
let messagesEl = document.getElementById('messages');
let inputEl = document.getElementById('chat-input');
let sendBtn = document.getElementById('send-btn');
let voiceBtn = document.getElementById('voice-btn');
let refreshBtn = document.getElementById('refresh-btn');
let boardBody = document.getElementById('board-body');
let boardTs = document.getElementById('board-timestamp');
let modeSelect = document.getElementById('mode-select');
let activeModel = document.getElementById('active-model');
let activeMode = document.getElementById('active-mode');

// ── WebSocket chat ──────────────────────────────
function connectWs() {
  if (ws) try { ws.close(); } catch(e) {}
  ws = new WebSocket(wsUrl);
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      removeTyping();
      addMessage('jarvis', data.response || '(empty)');
    } catch(_) {
      removeTyping();
      addMessage('jarvis', e.data);
    }
  };
  ws.onclose = () => { ws = null; setTimeout(connectWs, 3000); };
  ws.onerror = () => {};
}

function sendMessage(text) {
  if (!text.trim()) return;
  addMessage('user', text);
  showTyping();
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ message: text }));
  } else {
    // Fallback to REST
    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    }).then(r => r.json()).then(data => {
      removeTyping();
      addMessage('jarvis', data.response || '(empty)');
    }).catch(() => {
      removeTyping();
      addMessage('jarvis', 'Error: server unreachable');
    });
  }
  inputEl.value = '';
}

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  const label = document.createElement('div');
  label.className = 'label';
  label.textContent = role === 'user' ? 'YOU' : 'JARVIS';
  div.appendChild(label);
  const content = document.createElement('div');
  content.textContent = text;
  div.appendChild(content);
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showTyping() {
  removeTyping();
  const div = document.createElement('div');
  div.className = 'typing';
  div.id = 'typing-indicator';
  div.textContent = 'Jarvis is thinking...';
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

// ── Voice input (browser Web Speech API) ────────
voiceBtn.addEventListener('click', () => {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    addMessage('jarvis', 'Voice input not supported in this browser.');
    return;
  }
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new SR();
  rec.lang = 'en-US';
  rec.interimResults = false;
  rec.start();
  voiceBtn.textContent = '◉';
  rec.onresult = (e) => {
    const text = e.results[0][0].transcript;
    inputEl.value = text;
    voiceBtn.textContent = '🎤';
    sendMessage(text);
  };
  rec.onerror = () => { voiceBtn.textContent = '🎤'; };
  rec.onend = () => { voiceBtn.textContent = '🎤'; };
});

// ── Dev Board ───────────────────────────────────
function statusDot(ok) {
  if (ok === true) return '<span class="board-dot ok"></span>';
  if (ok === false) return '<span class="board-dot err"></span>';
  return '<span class="board-dot warn"></span>';
}

function fetchStatus() {
  fetch('/api/status')
    .then(r => r.json())
    .then(data => {
      boardBody.innerHTML = '';
      const sections = data.sections || {};
      Object.keys(sections).forEach(key => {
        const sec = sections[key];
        const sectionDiv = document.createElement('div');
        sectionDiv.className = 'board-section';
        const header = document.createElement('div');
        header.className = 'board-section-header';
        header.textContent = sec.label || key.toUpperCase();
        sectionDiv.appendChild(header);

        const items = sec.items || {};
        Object.keys(items).forEach(name => {
          const item = items[name];
          const row = document.createElement('div');
          row.className = 'board-item';
          const left = document.createElement('div');
          left.className = 'left';
          left.innerHTML = statusDot(item.ok);
          const nameSpan = document.createElement('span');
          nameSpan.className = 'name';
          nameSpan.textContent = name;
          left.appendChild(nameSpan);
          row.appendChild(left);
          const detail = document.createElement('span');
          detail.className = 'detail';
          detail.textContent = item.detail || '';
          row.appendChild(detail);
          sectionDiv.appendChild(row);
        });

        boardBody.appendChild(sectionDiv);
      });

      boardTs.textContent = 'updated ' + new Date(data.timestamp * 1000).toLocaleTimeString();
    })
    .catch(() => {
      boardBody.innerHTML = '<div class="board-item" style="padding:12px;color:var(--red)">Cannot reach server</div>';
    });
}

function fetchMeta() {
  fetch('/api/health')
    .then(r => r.json())
    .then(d => { if (d.model) activeModel.textContent = d.model; })
    .catch(() => {});
}

// ── Mode selector ───────────────────────────────
modeSelect.addEventListener('change', () => {
  const mode = modeSelect.value;
  fetch('/api/mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode })
  }).then(r => r.json()).then(d => {
    if (d.ok) activeMode.textContent = d.mode;
  }).catch(() => {});
});

// ── Events ──────────────────────────────────────
sendBtn.addEventListener('click', () => sendMessage(inputEl.value));
inputEl.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(inputEl.value); } });
refreshBtn.addEventListener('click', fetchStatus);

// ── Polling dev board every 10s ─────────────────
function init() {
  connectWs();
  fetchMeta();
  fetchStatus();
  setInterval(fetchStatus, 10000);
  setInterval(fetchMeta, 30000);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();

})();

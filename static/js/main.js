const msgEl      = document.getElementById("msg");
const btnEl      = document.getElementById("btn");
const messagesEl = document.getElementById("messages");

// Conversation state
let history    = [];   // [{role, content}]
let lastRecap  = null; // last recap payload

// ── Bootstrap greeting ─────────────────────────────────────────────────────
appendAssistant("text", "Hi! Ask me for a personalized match recap — e.g. <em>\"Show me Arjun's recap for India vs Pakistan\"</em> — or ask a follow-up question about the last match we discussed.");

// ── Input handling ─────────────────────────────────────────────────────────
msgEl.addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); send(); }
});

async function send() {
  const msg = msgEl.value.trim();
  if (!msg || btnEl.disabled) return;

  msgEl.value    = "";
  btnEl.disabled = true;

  appendUser(msg);
  const thinkingEl = appendThinking();

  try {
    const res  = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg, history, last_recap: lastRecap }),
    });
    const data = await res.json();

    thinkingEl.remove();

    if (!res.ok) {
      // HTTP error (404, 500, etc.)
      const detail = data.detail || "Something went wrong.";
      appendAssistant("error", escHtml(detail));
      history.push({ role: "user", content: msg });
      history.push({ role: "assistant", content: detail });
      return;
    }

    if (data.type === "recap") {
      lastRecap = data.data;
      appendAssistant("recap", data.data);
      history.push({ role: "user", content: msg });
      history.push({ role: "assistant", content: data.message }); // headline as context
    } else {
      appendAssistant("text", escHtml(data.message));
      history.push({ role: "user", content: msg });
      history.push({ role: "assistant", content: data.message });
    }

  } catch (e) {
    thinkingEl.remove();
    appendAssistant("error", "Network error: " + escHtml(e.message));
  } finally {
    btnEl.disabled = false;
    msgEl.focus();
  }
}

// ── Render helpers ─────────────────────────────────────────────────────────

function appendUser(text) {
  const row = document.createElement("div");
  row.className = "msg-row user";
  row.innerHTML = `<div class="bubble">${escHtml(text)}</div>`;
  messagesEl.appendChild(row);
  scrollBottom();
}

function appendThinking() {
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  row.innerHTML = `<div class="thinking"><span></span><span></span><span></span></div>`;
  messagesEl.appendChild(row);
  scrollBottom();
  return row;
}

function appendAssistant(type, payload) {
  const row = document.createElement("div");
  row.className = "msg-row assistant";

  if (type === "recap") {
    row.appendChild(buildRecapCard(payload));
  } else if (type === "error") {
    row.innerHTML = `<div class="bubble error-bubble">${payload}</div>`;
  } else {
    row.innerHTML = `<div class="bubble">${payload}</div>`;
  }

  messagesEl.appendChild(row);
  scrollBottom();
  return row;
}

function buildRecapCard(data) {
  const recap = data.recap;

  const highlights = recap.highlights.map(h => `
    <div class="highlight-item">
      <div class="highlight-moment">
        <span class="relevance">${h.relevance_score}</span>
        ${escHtml(h.moment)}
      </div>
      <div class="highlight-reason">${escHtml(h.why_relevant)}</div>
    </div>
  `).join("");

  const card = document.createElement("div");
  card.className = "recap-card";
  card.innerHTML = `
    <div class="recap-meta">
      <span class="recap-match">${escHtml(data.match)}</span>
      <div class="badges">
        <span class="badge">${escHtml(data.user)}</span>
        <span class="badge">${escHtml(data.interest_type.replace(/_/g, " "))}</span>
      </div>
    </div>
    <div class="recap-headline">${escHtml(recap.headline)}</div>
    <div class="recap-summary">${escHtml(recap.summary)}</div>
    <div class="section-title">Key Moments</div>
    <div class="highlights">${highlights}</div>
    <div class="section-title">Story of the Match</div>
    <div class="narrative">${escHtml(recap.narrative_thread)}</div>
  `;
  return card;
}

function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

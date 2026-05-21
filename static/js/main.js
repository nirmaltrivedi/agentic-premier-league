// ── Session ────────────────────────────────────────────────────────────────────
// A stable UUID for this page load — maps to one LangGraph MemorySaver thread
const SESSION_ID = crypto.randomUUID();

// ── DOM refs ───────────────────────────────────────────────────────────────────
const msgEl      = document.getElementById("msg");
const btnEl      = document.getElementById("btn");
const messagesEl = document.getElementById("messages");

// ── State ──────────────────────────────────────────────────────────────────────
let sessionEnded = false;

// ── Greeting ───────────────────────────────────────────────────────────────────
appendAssistant("text",
  'Hi! Ask me for a personalized match recap — e.g. <em>"Show me Arjun\'s recap for India vs Pakistan"</em> — ' +
  'or ask a follow-up question about the last match we discussed.'
);

// ── Input handling ─────────────────────────────────────────────────────────────
msgEl.addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); send(); }
});

async function send() {
  const msg = msgEl.value.trim();
  if (!msg || btnEl.disabled) return;

  msgEl.value    = "";
  btnEl.disabled = true;
  msgEl.disabled = true;

  appendUser(msg);

  // Progress indicator — replaced / removed as nodes fire
  const progressRow = appendProgress("Thinking…");

  try {
    const res = await fetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: SESSION_ID, message: msg }),
    });

    if (!res.ok) {
      progressRow.remove();
      appendAssistant("error", "Server error " + res.status);
      return;
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = "";

    // Track the live streaming bubble (for follow-up token streaming)
    let streamingRow    = null;
    let streamingBubble = null;
    let streamedText    = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete last line

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;

        const raw = line.slice(6).trim();
        if (raw === "[DONE]") break;

        let event;
        try { event = JSON.parse(raw); } catch { continue; }

        switch (event.type) {

          case "progress":
            progressRow.querySelector(".progress-label").textContent = event.label;
            break;

          case "recap":
            progressRow.remove();
            appendAssistant("recap", event.data);
            break;

          case "token":
            // First token — create streaming bubble
            if (!streamingRow) {
              progressRow.remove();
              streamingRow = document.createElement("div");
              streamingRow.className = "msg-row assistant";
              streamingBubble = document.createElement("div");
              streamingBubble.className = "bubble streaming-cursor";
              streamingRow.appendChild(streamingBubble);
              messagesEl.appendChild(streamingRow);
            }
            streamedText += event.text;
            streamingBubble.textContent = streamedText;
            scrollBottom();
            break;

          case "text_done":
            // Finalise streaming bubble — remove blinking cursor
            if (streamingBubble) {
              streamingBubble.classList.remove("streaming-cursor");
            }
            streamingRow = streamingBubble = null;
            streamedText = "";
            break;

          case "text":
            progressRow.remove();
            appendAssistant("text", escHtml(event.message));
            break;

          case "error":
            progressRow.remove();
            appendAssistant("error", escHtml(event.message));
            break;

          case "done_session":
            progressRow.remove();
            appendDoneSession();
            lockInput();
            break;
        }
      }
    }

  } catch (e) {
    progressRow.remove();
    appendAssistant("error", "Network error: " + escHtml(e.message));
  } finally {
    if (!sessionEnded) {
      btnEl.disabled = false;
      msgEl.disabled = false;
      msgEl.focus();
    }
  }
}

// ── Render helpers ─────────────────────────────────────────────────────────────

function appendUser(text) {
  const row = document.createElement("div");
  row.className = "msg-row user";
  row.innerHTML = `<div class="bubble">${escHtml(text)}</div>`;
  messagesEl.appendChild(row);
  scrollBottom();
}

function appendProgress(label) {
  const row = document.createElement("div");
  row.className = "progress-row";
  row.innerHTML = `
    <div class="progress-dots"><span></span><span></span><span></span></div>
    <span class="progress-label">${escHtml(label)}</span>
  `;
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
    // type === "text" — payload may contain safe HTML (e.g. <em> in greeting)
    row.innerHTML = `<div class="bubble">${payload}</div>`;
  }

  messagesEl.appendChild(row);
  scrollBottom();
  return row;
}

function appendDoneSession() {
  const el = document.createElement("div");
  el.className = "session-ended";
  el.textContent = "Session ended — refresh to start a new conversation";
  messagesEl.appendChild(el);
  scrollBottom();
}

function lockInput() {
  sessionEnded   = true;
  msgEl.disabled = true;
  btnEl.disabled = true;
  msgEl.placeholder = "Session ended. Refresh to start over.";
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

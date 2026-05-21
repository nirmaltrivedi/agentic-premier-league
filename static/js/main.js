const msgEl     = document.getElementById("msg");
const btnEl     = document.getElementById("btn");
const statusEl  = document.getElementById("status");
const recapCard = document.getElementById("recap-card");

msgEl.addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); send(); }
});

async function send() {
  const msg = msgEl.value.trim();
  if (!msg) return;

  btnEl.disabled = true;
  statusEl.className = "";
  statusEl.textContent = "Thinking...";
  recapCard.style.display = "none";

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg }),
    });
    const data = await res.json();

    if (!res.ok) {
      statusEl.className = "error";
      statusEl.textContent = data.detail || "Something went wrong.";
      return;
    }

    statusEl.textContent = "";
    renderRecap(data);

  } catch (e) {
    statusEl.className = "error";
    statusEl.textContent = "Network error: " + e.message;
  } finally {
    btnEl.disabled = false;
  }
}

function renderRecap(data) {
  document.getElementById("r-match").textContent    = data.match;
  document.getElementById("r-user").textContent     = data.user;
  document.getElementById("r-interest").textContent = data.interest_type.replace("_", " ");
  document.getElementById("r-headline").textContent = data.recap.headline;
  document.getElementById("r-summary").textContent  = data.recap.summary;
  document.getElementById("r-narrative").textContent = data.recap.narrative_thread;

  const container = document.getElementById("r-highlights");
  container.innerHTML = "";

  for (const h of data.recap.highlights) {
    const item = document.createElement("div");
    item.className = "highlight-item";
    item.innerHTML = `
      <div class="highlight-moment">
        <span class="relevance">${h.relevance_score}</span>
        ${escHtml(h.moment)}
      </div>
      <div class="highlight-reason">${escHtml(h.why_relevant)}</div>
    `;
    container.appendChild(item);
  }

  recapCard.style.display = "block";
}

function escHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

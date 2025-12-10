// Backend API base
const API_BASE = "http://127.0.0.1:8000";

// Core elements
const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("question-form");
const inputEl = document.getElementById("question-input");
const askBtn = document.getElementById("ask-button");

// Chat section
const chatSection = document.getElementById("chat-section");

// Floating buttons (only chat FAB now)
const fabChat = document.getElementById("fab-start-chat");

// Theme toggle
const themeToggle = document.getElementById("theme-toggle");

// FAQ + topic chips + claim help + TAT modal
const faqButtons = document.querySelectorAll(".faq-item");
const topicChips = document.querySelectorAll(".topic-chip");
const claimHelpBtn = document.getElementById("claim-help");
const tatOpenBtn = document.getElementById("view-tat");
const tatModal = document.getElementById("tat-modal");
const tatCloseBtn = document.getElementById("tat-close");

/* ---------- Utility ---------- */

function scrollToBottom() {
  if (!messagesEl) return;

  // If Lenis exists, temporarily stop it so native scroll can run without interference.
  const hasLenis = typeof lenis !== "undefined" && lenis && typeof lenis.stop === "function";
  if (hasLenis) {
    try { lenis.stop(); } catch (e) { /* ignore */ }
  }

  // Smoothly scroll the messages container to bottom
  requestAnimationFrame(() => {
    messagesEl.scrollTo({
      top: messagesEl.scrollHeight,
      behavior: "smooth",
    });
  });

  // Resume Lenis shortly after the scroll (after animation completes).
  if (hasLenis) {
    setTimeout(() => {
      try { lenis.start(); } catch (e) { /* ignore */ }
    }, 420);
  }
}

// Add a normal message bubble
function addMessage(text, role = "bot") {
  const div = document.createElement("div");
  div.classList.add("message", role);
  div.textContent = text;
  messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}

// Show typing indicator
function showTypingIndicator() {
  const div = document.createElement("div");
  div.classList.add("message", "bot", "typing");
  div.innerHTML = `
    <span class="typing-dot"></span>
    <span class="typing-dot"></span>
    <span class="typing-dot"></span>
  `;
  messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}

// Bot typewriter effect
function typeBotMessage(text) {
  const div = document.createElement("div");
  div.classList.add("message", "bot");
  messagesEl.appendChild(div);
  scrollToBottom();

  let index = 0;
  const speed = 20;

  function step() {
    if (index <= text.length) {
      div.textContent = text.slice(0, index);
      scrollToBottom();
      index++;
      setTimeout(step, speed);
    }
  }
  step();
}

/* ---------- API call ---------- */

async function askQuestion(question) {
  addMessage(question, "user");

  const typingIndicator = showTypingIndicator();

  askBtn.disabled = true;
  askBtn.textContent = "Thinking...";
  inputEl.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    if (!res.ok) throw new Error(`Server error: ${res.status}`);

    const data = await res.json();
    let answer = (data.answer || "No response.").replace(/\*\*/g, "");

    typingIndicator.remove();
    typeBotMessage(answer);

  } catch (err) {
    typingIndicator.remove();
    addMessage(`Error: ${err.message}`, "bot");
  } finally {
    askBtn.disabled = false;
    askBtn.textContent = "Ask";
    inputEl.disabled = false;
    inputEl.focus();
  }
}

/* ---------- Event wiring ---------- */

// Handle form submit
formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = inputEl.value.trim();
  if (!q) return;
  inputEl.value = "";
  askQuestion(q);
});

// Auto-focus input
window.addEventListener("load", () => {
  if (inputEl) inputEl.focus();
});

/* ---------- Floating Chat FAB ---------- */

if (fabChat) {
  fabChat.addEventListener("click", () => {
    chatSection.scrollIntoView({ behavior: "smooth" });
  });
}

/* ---------- Theme Toggle ---------- */

const savedTheme = localStorage.getItem("theme");
if (savedTheme === "dark") {
  document.body.classList.add("dark-mode");
  if (themeToggle) themeToggle.innerHTML = "☀️ Light mode";
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const isDark = document.body.classList.toggle("dark-mode");
    localStorage.setItem("theme", isDark ? "dark" : "light");
    themeToggle.innerHTML = isDark ? "☀️ Light mode" : "🌙 Dark mode";
  });
}

/* ---------- FAQ auto ask ---------- */

faqButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const q = btn.dataset.question;
    if (!q) return;
    askQuestion(q);
  });
});

/* ---------- Topic Chips ---------- */

topicChips.forEach((chip) => {
  chip.addEventListener("click", () => {
    const q = chip.dataset.question;
    if (!q) return;
    askQuestion(q);
  });
});

/* ---------- Claim Help shortcut ---------- */

if (claimHelpBtn) {
  claimHelpBtn.addEventListener("click", () => {
    const q = "How can I file a claim for my motor insurance policy?";
    askQuestion(q);
  });
}

/* ---------- TAT Modal ---------- */

if (tatOpenBtn && tatModal && tatCloseBtn) {
  tatOpenBtn.addEventListener("click", () => {
    tatModal.classList.add("open");
    tatModal.setAttribute("aria-hidden", "false");
  });

  tatCloseBtn.addEventListener("click", () => {
    tatModal.classList.remove("open");
    tatModal.setAttribute("aria-hidden", "true");
  });

  tatModal.addEventListener("click", (e) => {
    if (e.target === tatModal) {
      tatModal.classList.remove("open");
      tatModal.setAttribute("aria-hidden", "true");
    }
  });
}
// ----------------------
// Lenis Smooth Scroll
// ----------------------

const lenis = new Lenis({
  duration: 1.2,     // smoothness speed
  lerp: 0.1,         // inertia
  smooth: true,
  smoothTouch: true
});

function raf(time) {
  lenis.raf(time);
  requestAnimationFrame(raf);
}

requestAnimationFrame(raf);

/* ---------- Lenis / messages interaction: allow native scroll in .messages ---------- */
const messagesBox = messagesEl; // already grabbed above
// ---------- Force wheel/trackpad scrolling inside .messages ----------
if (messagesBox) {
  const onWheel = (e) => {
    // Only handle vertical scroll deltas
    if (Math.abs(e.deltaY) < Math.abs(e.deltaX)) return; // let horizontal gestures pass
    // If messages content is not scrollable, do nothing (let page scroll)
    if (messagesBox.scrollHeight <= messagesBox.clientHeight) return;

    // Compute new scroll position
    // Use deltaMode to normalize (0: pixels, 1: lines, 2: pages)
    let delta = e.deltaY;
    if (e.deltaMode === 1) delta *= 16; // lines -> px (approx)
    if (e.deltaMode === 2) delta *= messagesBox.clientHeight; // pages -> px

    // Apply scroll — do not allow the parent/page to also scroll
    messagesBox.scrollTop += delta;

    // Prevent the page / Lenis from also handling this wheel
    e.preventDefault();
    e.stopPropagation();
  };

  // Add non-passive listener so preventDefault works
  messagesBox.addEventListener("wheel", onWheel, { passive: false });

  // Optional: also handle "wheel" for Firefox/older (it uses wheel), and pointer/touch handled earlier
  // Clean up if needed:
  // messagesBox.removeEventListener("wheel", onWheel, { passive: false });
}

if (messagesBox) {
  // Pause Lenis when the mouse enters the messages area so wheel scroll affects .messages
  messagesBox.addEventListener("mouseenter", () => {
    if (typeof lenis !== "undefined" && lenis && typeof lenis.stop === "function") {
      try { lenis.stop(); } catch (e) { /* ignore */ }
    }
  });

  messagesBox.addEventListener("mouseleave", () => {
    if (typeof lenis !== "undefined" && lenis && typeof lenis.start === "function") {
      try { lenis.start(); } catch (e) { /* ignore */ }
    }
  });

  // Touch support: stop lenis on touchstart, resume on touchend
  messagesBox.addEventListener("touchstart", () => {
    if (typeof lenis !== "undefined" && lenis && typeof lenis.stop === "function") {
      try { lenis.stop(); } catch (e) { /* ignore */ }
    }
  }, { passive: true });

  messagesBox.addEventListener("touchend", () => {
    if (typeof lenis !== "undefined" && lenis && typeof lenis.start === "function") {
      try { lenis.start(); } catch (e) { /* ignore */ }
    }
  }, { passive: true });
}

/* ---------- End of File ---------- */
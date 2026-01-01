function formatBotText(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")   // bold
    .replace(/\n/g, "<br>");                            // line breaks
}
const API_BASE = "http://localhost:8000";

const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("question-form");
const inputEl = document.getElementById("question-input");
const faqListEl = document.getElementById("faq-list");
const faqWrapper = document.getElementById("faq-wrapper");
const faqToggle = document.getElementById("faq-toggle");

/* FAQ COLLAPSE */
faqToggle.addEventListener("click", () => {
  faqWrapper.classList.toggle("collapsed");
});

/* USER MESSAGE */
function addUser(text) {
  const msg = document.createElement("div");
  msg.className = "message user";
  msg.innerHTML = `<div class="bubble">${text}</div>`;
  messagesEl.appendChild(msg);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/* CHATGPT-LIKE TYPING */
function typeBot(text) {
  const msg = document.createElement("div");
  msg.className = "message bot";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  msg.appendChild(bubble);
  messagesEl.appendChild(msg);

  const formatted = formatBotText(text);
  let i = 0;

  function type() {
    if (i < formatted.length) {
      bubble.innerHTML = formatted.slice(0, i + 1);
      i++;
      messagesEl.scrollTop = messagesEl.scrollHeight;
      setTimeout(type, 18);
    }
  }

  type();
}

/* ASK QUESTION */
async function askQuestion(q) {
  addUser(q);
  inputEl.value = "";

  try {
    const res = await fetch(`${API_BASE}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q })
    });

    const data = await res.json();
    typeBot(data.answer);

  } catch {
    typeBot("Unable to connect to server.");
  }
}

/* FORM */
formEl.addEventListener("submit", e => {
  e.preventDefault();
  if (inputEl.value.trim()) askQuestion(inputEl.value.trim());
});

/* LOAD FAQS */
async function loadFAQs() {
  const res = await fetch(`${API_BASE}/faqs`);
  const data = await res.json();

  data.faqs.forEach(q => {
    const btn = document.createElement("button");
    btn.textContent = q;
    btn.onclick = () => askQuestion(q);
    faqListEl.appendChild(btn);
  });
}

loadFAQs();

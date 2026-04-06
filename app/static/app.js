const STORAGE_KEY = "songshanhu_chat_conversation_id";
const TOAST_DELAY_MS = 2200;

const STATUS_LABELS = {
  answered: "可答复",
  need_info: "待补充",
  handoff: "转人工",
  out_of_scope: "超范围",
};

const state = {
  conversationId: null,
  messages: [],
  health: null,
  conversations: [],
};

const elements = {
  messageList: document.getElementById("messageList"),
  messageInput: document.getElementById("messageInput"),
  chatForm: document.getElementById("chatForm"),
  sendBtn: document.getElementById("sendBtn"),
  preferLlmInput: document.getElementById("preferLlmInput"),
  refreshHealthBtn: document.getElementById("refreshHealthBtn"),
  newConversationBtn: document.getElementById("newConversationBtn"),
  healthBar: document.getElementById("healthBar"),
  conversationMeta: document.getElementById("conversationMeta"),
  historyList: document.getElementById("historyList"),
  historyCount: document.getElementById("historyCount"),
  toast: document.getElementById("toast"),
};

let toastTimer = null;

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function nowLabel(timestamp) {
  try {
    return new Date(timestamp).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function showToast(message) {
  if (!message) {
    return;
  }
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  if (toastTimer) {
    window.clearTimeout(toastTimer);
  }
  toastTimer = window.setTimeout(() => {
    elements.toast.classList.add("hidden");
  }, TOAST_DELAY_MS);
}

function setConversationMeta() {
  if (!state.conversationId) {
    elements.conversationMeta.classList.add("hidden");
    elements.conversationMeta.textContent = "";
    window.localStorage.removeItem(STORAGE_KEY);
    return;
  }

  const summary = state.conversations.find((item) => item.conversation_id === state.conversationId);
  const title = summary?.title || "当前咨询";
  const shortId = state.conversationId.slice(0, 8);
  elements.conversationMeta.classList.remove("hidden");
  elements.conversationMeta.textContent = `当前会话：${title} · ID ${shortId}`;
  window.localStorage.setItem(STORAGE_KEY, state.conversationId);
}

function factsSummary(facts) {
  const items = [];
  if (facts.child_hukou) items.push(`孩子户籍：${facts.child_hukou}`);
  if (facts.parent_hukou) items.push(`父母户籍：${facts.parent_hukou}`);
  if (facts.parent_work_in_songshanhu !== null && facts.parent_work_in_songshanhu !== undefined) {
    items.push(`父母在松山湖工作：${facts.parent_work_in_songshanhu ? "是" : "否"}`);
  }
  if (facts.has_songshanhu_property !== null && facts.has_songshanhu_property !== undefined) {
    items.push(`松山湖房产：${facts.has_songshanhu_property ? "有" : "无"}`);
  }
  if (facts.property_owner) items.push(`房产权属：${facts.property_owner}`);
  if (facts.stage) items.push(`申请学段：${facts.stage}`);
  if (facts.is_transfer !== null && facts.is_transfer !== undefined) {
    items.push(`是否转学：${facts.is_transfer ? "是" : "否"}`);
  }
  if (Array.isArray(facts.special_status) && facts.special_status.length) {
    items.push(`特殊情形：${facts.special_status.join("、")}`);
  }
  return items.length ? items.join(" / ") : "当前会话还没有记住明确条件。";
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status || "未知";
}

function renderHealth() {
  const health = state.health;
  if (!health) {
    elements.healthBar.innerHTML = '<span class="pill muted">连接中</span>';
    return;
  }

  elements.healthBar.innerHTML = [
    `<span class="pill ${health.ok ? "ok" : "danger"}">服务：${health.ok ? "正常" : "异常"}</span>`,
    `<span class="pill ${health.knowledge_loaded ? "ok" : "warn"}">知识库：${health.knowledge_loaded ? "已加载" : "未加载"}</span>`,
    `<span class="pill ${health.llm_enabled ? "ok" : "muted"}">LLM：${health.llm_enabled ? `${health.llm_provider} / ${health.default_model}` : "未启用"}</span>`,
    `<span class="pill ${health.openclaw_enabled ? "ok" : "warn"}">OpenClaw：${health.openclaw_enabled ? "可发送" : "未启用"}</span>`,
    `<span class="pill muted">人工热线：${escapeHtml(health.official_contact || "-")}</span>`,
  ].join("");
}

function renderHistory() {
  elements.historyCount.textContent = `${state.conversations.length} 条`;
  if (!state.conversations.length) {
    elements.historyList.innerHTML = '<p class="history-empty">还没有历史会话。</p>';
    return;
  }

  elements.historyList.innerHTML = state.conversations
    .map((item) => {
      const activeClass = item.conversation_id === state.conversationId ? " active" : "";
      const statusClass = item.status || "";
      return `
        <button class="history-item${activeClass}" type="button" data-conversation-id="${escapeHtml(item.conversation_id)}">
          <div class="history-top">
            <p class="history-title">${escapeHtml(item.title || "新对话")}</p>
            <span class="history-status ${statusClass}">${escapeHtml(statusLabel(item.status))}</span>
          </div>
          <p class="history-preview">${escapeHtml(item.preview || "暂无内容")}</p>
          <p class="history-time">${escapeHtml(nowLabel(item.updated_at))}</p>
        </button>
      `;
    })
    .join("");
}

function detailListMarkup(items) {
  if (!items || !items.length) {
    return "<li>无</li>";
  }
  return items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function evidenceListMarkup(items) {
  if (!items || !items.length) {
    return "<li>无</li>";
  }
  return items
    .map((item) => {
      const label = `${item.file_name}（${item.citation}）`;
      const title = item.source_url
        ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`
        : escapeHtml(label);
      return `<li>${title}<br>${escapeHtml(item.snippet || "")}</li>`;
    })
    .join("");
}

function detailsMarkup(answer, rememberedFacts) {
  const meta = [
    `<span class="meta-pill">问题类型：${escapeHtml(answer.question_type || "-")}</span>`,
    `<span class="meta-pill">状态：${escapeHtml(statusLabel(answer.status))}</span>`,
    `<span class="meta-pill">FAQ：${escapeHtml((answer.matched_faq_ids || []).join(", ") || "无")}</span>`,
    `<span class="meta-pill">LLM：${answer.used_llm ? "是" : "否"}</span>`,
  ].join("");

  return `
    <div class="answer-meta">${meta}</div>
    <div class="message-actions">
      <button class="message-action primary" type="button" data-action="copy-reply">复制客服回复</button>
      <button class="message-action" type="button" data-action="copy-handoff">人工转接</button>
    </div>
    <details class="answer-details">
      <summary>查看依据、建议和记忆上下文</summary>
      <div class="detail-grid">
        <div class="detail-block">
          <p class="detail-title">建议信息</p>
          <p class="bubble-body">${escapeHtml(answer.consultation_advice || "无")}</p>
        </div>
        <div class="detail-block">
          <p class="detail-title">不能确认的理由</p>
          <p class="bubble-body">${escapeHtml(answer.cannot_confirm_reason || "无")}</p>
        </div>
        <div class="detail-block">
          <p class="detail-title">仍需补充的信息</p>
          <ul class="detail-list">${detailListMarkup(answer.missing_fields || [])}</ul>
        </div>
        <div class="detail-block">
          <p class="detail-title">适用前提</p>
          <ul class="detail-list">${detailListMarkup(answer.applicable_conditions || [])}</ul>
        </div>
        <div class="detail-block full">
          <p class="detail-title">依据</p>
          <ul class="detail-list">${evidenceListMarkup(answer.evidence || [])}</ul>
        </div>
        <div class="detail-block">
          <p class="detail-title">风险提示</p>
          <ul class="detail-list">${detailListMarkup(answer.risk_notice || [])}</ul>
        </div>
        <div class="detail-block">
          <p class="detail-title">建议下一步</p>
          <p class="bubble-body">${escapeHtml(answer.next_step || "无")}</p>
        </div>
      </div>
      <div class="memory-strip">已记住：${escapeHtml(factsSummary(rememberedFacts || {}))}</div>
    </details>
  `;
}

function messageTemplate(item, index) {
  const isAssistant = item.role === "assistant";
  const isSystem = item.role === "system";
  const roleLabel = isAssistant ? "助手" : isSystem ? "系统" : "你";
  const avatarLabel = isAssistant ? "咨" : isSystem ? "系" : "你";
  const badge = isAssistant && item.answer
    ? `<span class="status-badge ${item.answer.status}">${escapeHtml(statusLabel(item.answer.status))}</span>`
    : "";
  const details = isAssistant && item.answer ? detailsMarkup(item.answer, item.rememberedFacts) : "";

  return `
    <article class="message ${item.role}" data-message-index="${index}">
      <div class="bubble-wrap">
        <div class="bubble-avatar ${item.role}" aria-hidden="true">${avatarLabel}</div>
        <div class="bubble">
          <div class="bubble-head">
            <span class="bubble-role">${roleLabel}</span>
            <div>
              ${badge}
              <span class="bubble-time">${escapeHtml(nowLabel(item.timestamp))}</span>
            </div>
          </div>
          <p class="bubble-body">${escapeHtml(item.content)}</p>
          ${details}
        </div>
      </div>
    </article>
  `;
}

function renderMessages() {
  if (!state.messages.length) {
    elements.messageList.innerHTML = `
      <div class="empty-state">
        <div>
          <p>直接开始提问即可。</p>
          <p>例如：我家孩子能报哪一类？</p>
        </div>
      </div>
    `;
    return;
  }

  elements.messageList.innerHTML = state.messages.map((item, index) => messageTemplate(item, index)).join("");
  elements.messageList.scrollTop = elements.messageList.scrollHeight;
}

function normalizeHistory(history, rememberedFacts) {
  return (history || []).map((item) => ({
    ...item,
    rememberedFacts: item.role === "assistant" ? rememberedFacts : null,
  }));
}

async function fetchHealth() {
  const response = await fetch("/health");
  state.health = await response.json();
  renderHealth();
}

async function fetchConversations() {
  const response = await fetch("/conversations");
  const payload = await response.json();
  state.conversations = payload.items || [];
  renderHistory();
  setConversationMeta();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

function resetConversation() {
  state.conversationId = null;
  state.messages = [];
  renderMessages();
  setConversationMeta();
  renderHistory();
}

async function loadConversation(conversationId) {
  if (!conversationId) {
    return;
  }
  const payload = await getJson(`/chat/${conversationId}`);
  state.conversationId = payload.conversation_id;
  state.messages = normalizeHistory(payload.history, payload.remembered_facts);
  renderMessages();
  setConversationMeta();
  renderHistory();
}

async function restoreConversation() {
  const savedId = window.localStorage.getItem(STORAGE_KEY);
  if (!savedId) {
    resetConversation();
    return;
  }

  try {
    await loadConversation(savedId);
  } catch {
    resetConversation();
  }
}

async function copyText(text, successMessage) {
  const value = String(text || "").trim();
  if (!value) {
    showToast("没有可复制的内容。");
    return;
  }

  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    showToast(successMessage);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
  showToast(successMessage);
}

async function handleSend(event) {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message) {
    return;
  }

  const optimisticUserMessage = {
    role: "user",
    content: message,
    timestamp: new Date().toISOString(),
  };
  state.messages.push(optimisticUserMessage);
  renderMessages();
  elements.messageInput.value = "";
  elements.sendBtn.disabled = true;

  try {
    const payload = await postJson("/chat", {
      conversation_id: state.conversationId,
      message,
      prefer_llm: elements.preferLlmInput.checked,
    });
    state.conversationId = payload.conversation_id;
    state.messages = normalizeHistory(payload.history, payload.remembered_facts);
    await fetchConversations();
    renderMessages();
    setConversationMeta();
  } catch (error) {
    state.messages.push({
      role: "system",
      content: `请求失败：${error.message || error}`,
      timestamp: new Date().toISOString(),
    });
    renderMessages();
  } finally {
    elements.sendBtn.disabled = false;
    elements.messageInput.focus();
  }
}

document.querySelectorAll(".example-chip").forEach((button) => {
  button.addEventListener("click", () => {
    elements.messageInput.value = button.dataset.question || "";
    elements.messageInput.focus();
  });
});

elements.chatForm.addEventListener("submit", handleSend);
elements.refreshHealthBtn.addEventListener("click", fetchHealth);
elements.newConversationBtn.addEventListener("click", () => {
  resetConversation();
  showToast("已开始新咨询。");
});

elements.historyList.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-conversation-id]");
  if (!target) {
    return;
  }
  try {
    await loadConversation(target.dataset.conversationId);
  } catch (error) {
    showToast(`加载会话失败：${error.message || error}`);
  }
});

elements.messageList.addEventListener("click", async (event) => {
  const action = event.target.closest("[data-action]");
  if (!action) {
    return;
  }
  const container = event.target.closest("[data-message-index]");
  if (!container) {
    return;
  }
  const index = Number(container.dataset.messageIndex);
  const message = state.messages[index];
  if (!message?.answer) {
    return;
  }

  if (action.dataset.action === "copy-reply") {
    await copyText(message.answer.customer_reply, "客服回复已复制。");
    return;
  }
  if (action.dataset.action === "copy-handoff") {
    await copyText(message.answer.handoff_message, "人工转接内容已复制。");
  }
});

async function bootstrap() {
  renderMessages();
  await Promise.all([fetchHealth(), fetchConversations()]);
  await restoreConversation();
}

bootstrap().catch((error) => {
  state.messages = [
    {
      role: "system",
      content: `初始化失败：${error.message || error}`,
      timestamp: new Date().toISOString(),
    },
  ];
  renderMessages();
});

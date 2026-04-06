import {
  apiGet,
  apiPost,
  compactPreview,
  conversationChannelLabel,
  escapeHtml,
  factsSummary,
  formatTime,
  statusLabel,
  takeoverLabel,
} from "./shared.js";

const STORAGE_KEY = "songshanhu_parent_conversation_v3";
const TOAST_DELAY_MS = 2200;

const state = {
  conversationId: window.localStorage.getItem(STORAGE_KEY) || null,
  conversations: [],
  history: [],
  rememberedFacts: {},
  currentConversation: null,
  health: null,
  isSubmitting: false,
  pendingTurnId: 0,
};

const elements = {
  historyList: document.getElementById("historyList"),
  historyCount: document.getElementById("historyCount"),
  healthBar: document.getElementById("healthBar"),
  refreshBtn: document.getElementById("refreshBtn"),
  newConversationBtn: document.getElementById("newConversationBtn"),
  chatTimeline: document.getElementById("chatTimeline"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  chatSubmit: document.querySelector('#chatForm button[type="submit"]'),
  conversationMeta: document.getElementById("conversationMeta"),
  toast: document.getElementById("toast"),
};

let toastTimer = null;

function showToast(message) {
  if (!message) {
    return;
  }
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    elements.toast.classList.add("hidden");
  }, TOAST_DELAY_MS);
}

function activeConversationSummary() {
  return state.conversations.find((item) => item.conversation_id === state.conversationId) || null;
}

function activeConversationLabel() {
  const snapshot = state.currentConversation;
  if (snapshot?.manual_takeover) {
    return `人工状态：${takeoverLabel(snapshot.takeover_status)}`;
  }
  return "机器人跟进中";
}

function renderHealth() {
  if (!state.health) {
    elements.healthBar.innerHTML = '<span class="pill">连接中</span>';
    return;
  }
  elements.healthBar.innerHTML = [
    `<span class="pill ${state.health.ok ? "ok" : "danger"}">服务 ${state.health.ok ? "正常" : "异常"}</span>`,
    `<span class="pill ${state.health.knowledge_loaded ? "ok" : "warn"}">知识库 ${state.health.knowledge_loaded ? "已加载" : "未加载"}</span>`,
    `<span class="pill ${state.health.openclaw_enabled ? "accent" : "warn"}">OpenClaw ${state.health.openclaw_enabled ? "已联通" : "未发送"}</span>`,
    `<span class="pill accent">${escapeHtml(state.health.official_contact || "-")}</span>`,
  ].join("");
}

function renderHistory() {
  elements.historyCount.textContent = `${state.conversations.length} 条`;
  if (!state.conversations.length) {
    elements.historyList.innerHTML = '<div class="empty-state">还没有咨询记录。直接在右侧输入问题即可。</div>';
    return;
  }
  elements.historyList.innerHTML = state.conversations
    .map((item) => {
      const active = item.conversation_id === state.conversationId ? " active" : "";
      item.preview = compactPreview(item.preview || item.preview);
      const tags = [
        `<span class="tag accent">${escapeHtml(conversationChannelLabel(item))}</span>`,
        `<span class="tag ${item.status === "answered" ? "ok" : item.status === "need_info" ? "warn" : "danger"}">${escapeHtml(statusLabel(item.status))}</span>`,
      ];
      if (item.manual_takeover) {
        tags.push(`<span class="tag warn">${escapeHtml(takeoverLabel(item.takeover_status))}</span>`);
      }
      return `
        <button class="history-item${active}" type="button" data-conversation-id="${escapeHtml(item.conversation_id)}">
          <div class="split-row">
            <p class="history-title">${escapeHtml(item.title || "新对话")}</p>
            <span class="timeline-time">${escapeHtml(formatTime(item.updated_at))}</span>
          </div>
          <p class="history-preview">${escapeHtml(item.preview || "暂无内容")}</p>
          <div class="tag-row">${tags.join("")}</div>
        </button>
      `;
    })
    .join("");
}

function renderConversationMeta() {
  const summary = activeConversationSummary() || state.currentConversation;
  if (!state.conversationId || !summary) {
    elements.conversationMeta.textContent = "未选择会话";
    window.localStorage.removeItem(STORAGE_KEY);
    return;
  }
  elements.conversationMeta.textContent = [
    summary.title || "当前会话",
    conversationChannelLabel(summary),
    activeConversationLabel(),
    `最近更新 ${formatTime(summary.updated_at)}`,
  ].join(" / ");
  window.localStorage.setItem(STORAGE_KEY, state.conversationId);
}

function detailListMarkup(items, fallback = "无") {
  if (!items || !items.length) {
    return `<li>${escapeHtml(fallback)}</li>`;
  }
  return items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function evidenceListMarkup(items) {
  if (!items || !items.length) {
    return "<li>无</li>";
  }
  return items
    .map((item) => {
      const title = `${item.file_name || "未命名来源"}（${item.citation || "未标注"}）`;
      const linkedTitle = item.source_url
        ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(title)}</a>`
        : escapeHtml(title);
      return `<li>${linkedTitle}<br>${escapeHtml(item.snippet || "未提供摘要")}</li>`;
    })
    .join("");
}

function assistantMemoryFor(item) {
  return item.answer?.session_update?.retained_profile || state.rememberedFacts || {};
}

function assistantDetailMarkup(answer, rememberedFacts) {
  return `
    <div class="message-actions">
      <button class="ghost-button compact-button" type="button" data-action="copy-reply">复制客服回复</button>
      <button class="secondary-button compact-button" type="button" data-action="handoff">人工转接</button>
    </div>
    <details class="answer-details">
      <summary>查看建议、依据和当前记忆上下文</summary>
      <div class="detail-grid">
        <article class="detail-block">
          <p class="block-title">建议信息</p>
          <p class="message-body">${escapeHtml(answer.consultation_advice || "无")}</p>
        </article>
        <article class="detail-block">
          <p class="block-title">不能确认的理由</p>
          <p class="message-body">${escapeHtml(answer.cannot_confirm_reason || "无")}</p>
        </article>
        <article class="detail-block">
          <p class="block-title">仍需补充的信息</p>
          <ul class="detail-list">${detailListMarkup(answer.missing_fields, "无")}</ul>
        </article>
        <article class="detail-block">
          <p class="block-title">建议下一步</p>
          <p class="message-body">${escapeHtml(answer.next_step || "无")}</p>
        </article>
        <article class="detail-block full">
          <p class="block-title">依据</p>
          <ul class="detail-list">${evidenceListMarkup(answer.evidence)}</ul>
        </article>
        <article class="detail-block">
          <p class="block-title">风险提醒</p>
          <ul class="detail-list">${detailListMarkup(answer.risk_notice, "无")}</ul>
        </article>
        <article class="detail-block">
          <p class="block-title">当前已记住的条件</p>
          <p class="message-body">${escapeHtml(factsSummary(rememberedFacts))}</p>
        </article>
      </div>
    </details>
  `;
}

function messageTemplate(item, index) {
  const isAssistant = item.role === "assistant";
  const isPending = Boolean(item.pending);
  const roleLabel = isAssistant ? "咨询助手" : item.role === "system" ? "系统" : "你";
  const avatarLabel = isAssistant ? "咨" : item.role === "system" ? "系" : "你";
  const badge = isPending && isAssistant
    ? '<span class="tag accent">回应中</span>'
    : isAssistant && item.answer
      ? `<span class="tag ${item.answer.status === "answered" ? "ok" : item.answer.status === "need_info" ? "warn" : "danger"}">${escapeHtml(statusLabel(item.answer.status))}</span>`
      : "";
  const details = isAssistant && item.answer
    ? assistantDetailMarkup(item.answer, assistantMemoryFor(item))
    : "";
  const pendingDots = isPending && isAssistant
    ? '<span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span>'
    : "";

  return `
    <article class="message ${item.role}${isPending ? " pending" : ""}" data-message-index="${index}">
      <div class="message-frame ${item.role === "user" ? "reverse" : ""}">
        <div class="message-avatar ${item.role}" aria-hidden="true">${avatarLabel}</div>
        <div class="message-panel ${item.role}">
          <div class="message-head">
            <div class="split-row">
              <p class="message-role">${roleLabel}</p>
              <span class="timeline-time">${escapeHtml(formatTime(item.timestamp))}</span>
            </div>
            ${badge}
          </div>
          <p class="message-body">${escapeHtml(item.content)}${pendingDots}</p>
          ${details}
        </div>
      </div>
    </article>
  `;
}

function renderTimeline() {
  if (!state.history.length) {
    elements.chatTimeline.innerHTML = `
      <div class="empty-state">
        直接开始提问即可。例如：今年的最新政策是怎样的，简单说一下；或者：帮我做资格预判，孩子是东莞其他镇街户籍，父母在松山湖工作，没有房产。
      </div>
    `;
    return;
  }
  elements.chatTimeline.innerHTML = state.history.map((item, index) => messageTemplate(item, index)).join("");
  elements.chatTimeline.scrollTop = elements.chatTimeline.scrollHeight;
}

function setComposerBusy(isBusy) {
  state.isSubmitting = isBusy;
  elements.chatInput.disabled = isBusy;
  if (elements.chatSubmit) {
    elements.chatSubmit.disabled = isBusy;
    elements.chatSubmit.textContent = isBusy ? "系统正在回应...." : "发送咨询";
  }
}

function appendPendingTurns(message) {
  state.pendingTurnId += 1;
  const pendingId = `pending-${Date.now()}-${state.pendingTurnId}`;
  const timestamp = new Date().toISOString();
  state.history = [
    ...state.history,
    {
      id: `${pendingId}-user`,
      role: "user",
      content: message,
      timestamp,
      pending: true,
    },
    {
      id: `${pendingId}-assistant`,
      role: "assistant",
      content: "系统正在回应....",
      timestamp,
      pending: true,
    },
  ];
  renderTimeline();
}

function replacePendingTurnsWithError(message) {
  const timestamp = new Date().toISOString();
  state.history = [
    ...state.history.filter((item) => !item.pending),
    {
      role: "user",
      content: message,
      timestamp,
    },
    {
      role: "system",
      content: "系统回应失败，请稍后重试。",
      timestamp,
    },
  ];
  renderTimeline();
}

async function copyText(value, successMessage) {
  const text = String(value || "").trim();
  if (!text) {
    showToast("没有可复制的内容。");
    return;
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    showToast(successMessage);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
  showToast(successMessage);
}

async function fetchHealth() {
  state.health = await apiGet("/health");
  renderHealth();
}

async function fetchConversations() {
  const payload = await apiGet("/conversations");
  state.conversations = payload.items || [];
  renderHistory();
  renderConversationMeta();
}

function applyConversationSnapshot(payload) {
  state.conversationId = payload.conversation_id;
  state.history = payload.history || [];
  state.rememberedFacts = payload.remembered_facts || {};
  state.currentConversation = payload;
  renderConversationMeta();
  renderHistory();
  renderTimeline();
}

async function loadConversation(conversationId) {
  if (!conversationId) {
    return;
  }
  const payload = await apiGet(`/chat/${conversationId}`);
  applyConversationSnapshot(payload);
}

async function restoreConversation() {
  const savedId = window.localStorage.getItem(STORAGE_KEY);
  if (!savedId) {
    renderConversationMeta();
    renderTimeline();
    return;
  }
  try {
    await loadConversation(savedId);
  } catch {
    resetConversation();
  }
}

function resetConversation() {
  state.conversationId = null;
  state.history = [];
  state.rememberedFacts = {};
  state.currentConversation = null;
  window.localStorage.removeItem(STORAGE_KEY);
  renderConversationMeta();
  renderTimeline();
  renderHistory();
}

async function sendChatMessage(message) {
  const payload = await apiPost("/chat", {
    conversation_id: state.conversationId,
    message,
    prefer_llm: Boolean(state.health?.llm_enabled),
    channel: "web",
    entry_point: "quick_qa",
  });
  applyConversationSnapshot(payload);
  void fetchConversations().catch((error) => {
    console.error("Failed to refresh conversations.", error);
  });
}

async function handleChatSubmission(rawMessage) {
  const message = String(rawMessage || "").trim();
  if (!message || state.isSubmitting) {
    return;
  }
  appendPendingTurns(message);
  setComposerBusy(true);
  try {
    await sendChatMessage(message);
  } catch (error) {
    replacePendingTurnsWithError(message);
    showToast(`鍙戦€佸け璐ワ細${error.message || error}`);
  } finally {
    setComposerBusy(false);
    elements.chatInput.focus();
  }
}

async function requestTakeover(answer) {
  if (!state.conversationId) {
    showToast("当前还没有可转接的会话。");
    return;
  }
  await apiPost(`/ops/conversations/${state.conversationId}/takeover`, {
    agent_name: "人工客服",
    note: "家长在前台点击人工转接",
    status: "requested",
  });
  await fetchConversations();
  await loadConversation(state.conversationId);
  if (answer?.handoff_message) {
    await copyText(answer.handoff_message, "已提交人工转接，并复制转接说明。");
    return;
  }
  showToast("已提交人工转接。");
}

function bindExampleChips() {
  document.querySelectorAll(".quick-chip").forEach((button) => {
    button.addEventListener("click", async () => {
      const question = button.dataset.question || "";
      if (!question) {
        return;
      }
      elements.chatInput.value = "";
      await handleChatSubmission(question);
    });
  });
}

function bindEvents() {
  elements.refreshBtn.addEventListener("click", async () => {
    await Promise.all([fetchHealth(), fetchConversations()]);
    if (state.conversationId) {
      await loadConversation(state.conversationId);
    }
    showToast("已刷新。");
  });

  elements.newConversationBtn.addEventListener("click", () => {
    resetConversation();
    showToast("已开始新会话。");
    elements.chatInput.focus();
  });

  elements.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = elements.chatInput.value.trim();
    if (!message) {
      return;
    }
    elements.chatInput.value = "";
    try {
      await handleChatSubmission(message);
    } catch (error) {
      showToast(`发送失败：${error.message || error}`);
    } finally {
      elements.chatInput.focus();
    }
  });

  elements.historyList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-conversation-id]");
    if (!button) {
      return;
    }
    try {
      await loadConversation(button.dataset.conversationId);
    } catch (error) {
      showToast(`加载会话失败：${error.message || error}`);
    }
  });

  elements.chatTimeline.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-action]");
    if (!action) {
      return;
    }
    const container = event.target.closest("[data-message-index]");
    if (!container) {
      return;
    }
    const index = Number(container.dataset.messageIndex);
    const turn = state.history[index];
    const answer = turn?.answer;
    if (!answer) {
      return;
    }
    try {
      if (action.dataset.action === "copy-reply") {
        await copyText(answer.customer_reply, "客服回复已复制。");
        return;
      }
      if (action.dataset.action === "handoff") {
        await requestTakeover(answer);
      }
    } catch (error) {
      showToast(`操作失败：${error.message || error}`);
    }
  });
}

async function bootstrap() {
  renderTimeline();
  bindExampleChips();
  bindEvents();
  await Promise.all([fetchHealth(), fetchConversations()]);
  await restoreConversation();
}

bootstrap().catch((error) => {
  console.error(error);
  showToast("页面初始化失败，请刷新后重试。");
});

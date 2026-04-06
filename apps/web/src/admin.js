import {
  compactPreview,
  conversationChannelLabel,
  escapeHtml,
  factsSummary,
  formatTime,
  statusLabel,
  takeoverLabel,
} from "./shared.js";

const state = {
  dashboard: null,
  conversations: [],
  selectedConversationId: null,
  selectedConversation: null,
  activeTab: "conversations",
  adminSession: {
    authenticated: false,
    login_enabled: false,
    username: null,
  },
};

const elements = {
  adminLoginShell: document.getElementById("adminLoginShell"),
  adminAppShell: document.getElementById("adminAppShell"),
  adminLoginForm: document.getElementById("adminLoginForm"),
  adminUsername: document.getElementById("adminUsername"),
  adminPassword: document.getElementById("adminPassword"),
  adminLoginHint: document.getElementById("adminLoginHint"),
  adminLoginSubmit: document.getElementById("adminLoginSubmit"),
  refreshDashboardBtn: document.getElementById("refreshDashboardBtn"),
  adminLogoutBtn: document.getElementById("adminLogoutBtn"),
  metricGrid: document.getElementById("metricGrid"),
  takeoverQueue: document.getElementById("takeoverQueue"),
  conversationCount: document.getElementById("conversationCount"),
  conversationList: document.getElementById("conversationList"),
  detailTags: document.getElementById("detailTags"),
  conversationDetail: document.getElementById("conversationDetail"),
  questionHeat: document.getElementById("questionHeat"),
  unmatchedPool: document.getElementById("unmatchedPool"),
  staleDocs: document.getElementById("staleDocs"),
  aliasForm: document.getElementById("aliasForm"),
  aliasList: document.getElementById("aliasList"),
  repairForm: document.getElementById("repairForm"),
  repairList: document.getElementById("repairList"),
  selectedConversationTip: document.getElementById("selectedConversationTip"),
  adminWorkspaceTabs: document.getElementById("adminWorkspaceTabs"),
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
  }, 2400);
}

function activeSummary() {
  return state.conversations.find((item) => item.conversation_id === state.selectedConversationId) || null;
}

function renderWorkspaceTabs() {
  const buttons = elements.adminWorkspaceTabs?.querySelectorAll("[data-tab]") || [];
  const panels = document.querySelectorAll("[data-tab-panel]");
  buttons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === state.activeTab);
  });
  panels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tabPanel === state.activeTab);
  });
}

function setActiveTab(tab) {
  state.activeTab = tab || "conversations";
  renderWorkspaceTabs();
}

function applyAdminSession(session) {
  state.adminSession = {
    authenticated: Boolean(session?.authenticated),
    login_enabled: Boolean(session?.login_enabled),
    username: session?.username || null,
  };

  const authenticated = state.adminSession.authenticated;
  const loginEnabled = state.adminSession.login_enabled;
  elements.adminLoginShell.classList.toggle("hidden", authenticated);
  elements.adminAppShell.classList.toggle("hidden", !authenticated);
  elements.adminLoginShell.hidden = authenticated;
  elements.adminAppShell.hidden = !authenticated;
  elements.adminLoginShell.setAttribute("aria-hidden", authenticated ? "true" : "false");
  elements.adminAppShell.setAttribute("aria-hidden", authenticated ? "false" : "true");

  if (!authenticated) {
    elements.adminPassword.value = "";
  }

  elements.adminUsername.disabled = !loginEnabled;
  elements.adminPassword.disabled = !loginEnabled;
  elements.adminLoginSubmit.disabled = !loginEnabled;

  if (!loginEnabled) {
    elements.adminLoginHint.textContent = "后台尚未配置登录密码，请先在服务器环境变量中设置 ADMIN_PASSWORD。";
    return;
  }
  if (authenticated) {
    elements.adminLoginHint.textContent = `当前登录账号：${state.adminSession.username || "admin"}`;
    return;
  }
  elements.adminLoginHint.textContent = "请输入后台账号和密码。";
}

function clearWorkspace() {
  state.dashboard = null;
  state.conversations = [];
  state.selectedConversationId = null;
  state.selectedConversation = null;
  renderMetrics();
  renderTakeoverQueue();
  renderConversations();
  renderDashboardLists();
  renderConversationDetail();
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
  });
  const text = await response.text();
  if (!response.ok) {
    const error = new Error(text || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return text ? JSON.parse(text) : {};
}

async function fetchAdminSession() {
  return fetchJson("/admin/session");
}

async function adminLogin(username, password) {
  return fetchJson("/admin/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify({ username, password }),
  });
}

async function adminLogout() {
  return fetchJson("/admin/logout", {
    method: "POST",
    headers: {
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify({}),
  });
}

async function adminGet(url) {
  try {
    return await fetchJson(url);
  } catch (error) {
    if (error.status === 401) {
      applyAdminSession(await fetchAdminSession());
      clearWorkspace();
      throw new Error("后台登录已失效，请重新登录。");
    }
    throw error;
  }
}

async function adminPost(url, payload) {
  try {
    return await fetchJson(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    if (error.status === 401) {
      applyAdminSession(await fetchAdminSession());
      clearWorkspace();
      throw new Error("后台登录已失效，请重新登录。");
    }
    throw error;
  }
}

function renderMetrics() {
  const dashboard = state.dashboard;
  if (!dashboard) {
    elements.metricGrid.innerHTML = '<div class="empty-state">登录后可查看运营指标。</div>';
    return;
  }
  const metrics = [
    { label: "FAQ 命中率", value: `${dashboard.faq_hit_rate.ratio}%`, note: `${dashboard.faq_hit_rate.numerator}/${dashboard.faq_hit_rate.denominator}` },
    { label: "规则命中率", value: `${dashboard.rule_hit_rate.ratio}%`, note: `${dashboard.rule_hit_rate.numerator}/${dashboard.rule_hit_rate.denominator}` },
    { label: "OpenClaw 会话", value: String(dashboard.openclaw_conversations), note: "来源于 OpenClaw 的历史会话" },
    { label: "待人工接管", value: String(dashboard.pending_takeovers), note: "人工队列 + 异常会话" },
  ];
  elements.metricGrid.innerHTML = metrics
    .map(
      (item) => `
        <article class="metric-card">
          <p class="metric-label">${escapeHtml(item.label)}</p>
          <p class="metric-value">${escapeHtml(item.value)}</p>
          <p class="metric-note">${escapeHtml(item.note)}</p>
        </article>
      `,
    )
    .join("");
}

function renderTakeoverQueue() {
  const items = state.dashboard?.takeover_queue || [];
  if (!items.length) {
    elements.takeoverQueue.innerHTML = '<div class="empty-state">当前没有待关注会话。</div>';
    return;
  }
  elements.takeoverQueue.innerHTML = items
    .map((item) => {
      const preview = compactPreview(item.preview || "");
      return `
        <button class="conversation-card ${item.conversation_id === state.selectedConversationId ? "active" : ""}" type="button" data-conversation-id="${escapeHtml(item.conversation_id)}">
          <div class="split-row">
            <p class="history-title">${escapeHtml(item.title)}</p>
            <span class="timeline-time">${escapeHtml(formatTime(item.updated_at))}</span>
          </div>
          <p class="history-preview">${escapeHtml(preview || "暂无摘要")}</p>
          <div class="conversation-meta">
            <span class="tag accent">${escapeHtml(conversationChannelLabel(item))}</span>
            <span class="tag ${item.status === "handoff" ? "danger" : item.status === "need_info" ? "warn" : "ok"}">${escapeHtml(statusLabel(item.status))}</span>
            <span class="tag warn">${escapeHtml(takeoverLabel(item.takeover_status))}</span>
          </div>
        </button>
      `;
    })
    .join("");
}

function renderConversations() {
  elements.conversationCount.textContent = `${state.conversations.length} 条`;
  if (!state.conversations.length) {
    elements.conversationList.innerHTML = '<div class="empty-state">暂无会话。</div>';
    return;
  }
  elements.conversationList.innerHTML = state.conversations
    .map((item) => {
      const preview = compactPreview(item.preview || "");
      return `
        <button class="conversation-card ${item.conversation_id === state.selectedConversationId ? "active" : ""}" type="button" data-conversation-id="${escapeHtml(item.conversation_id)}">
          <div class="split-row">
            <p class="history-title">${escapeHtml(item.title)}</p>
            <span class="timeline-time">${escapeHtml(formatTime(item.updated_at))}</span>
          </div>
          <p class="history-preview">${escapeHtml(preview || "暂无摘要")}</p>
          <div class="conversation-meta">
            <span class="tag accent">${escapeHtml(conversationChannelLabel(item))}</span>
            <span class="tag ${item.status === "handoff" ? "danger" : item.status === "need_info" ? "warn" : "ok"}">${escapeHtml(statusLabel(item.status))}</span>
            <span class="tag accent">${escapeHtml(item.last_resolution_source || "-")}</span>
            ${item.manual_takeover ? '<span class="tag warn">人工处理中</span>' : ""}
          </div>
        </button>
      `;
    })
    .join("");
}

function renderSimpleList(container, items, renderItem, emptyText) {
  if (!items.length) {
    container.innerHTML = `<div class="empty-state">${escapeHtml(emptyText)}</div>`;
    return;
  }
  container.innerHTML = items.map(renderItem).join("");
}

function renderDashboardLists() {
  const dashboard = state.dashboard;
  renderSimpleList(
    elements.questionHeat,
    dashboard?.question_heat || [],
    (item) => `
      <article class="list-item">
        <div class="split-row">
          <h3>${escapeHtml(item.question)}</h3>
          <span class="tag accent">${escapeHtml(String(item.hits))} 次</span>
        </div>
        <div class="conversation-meta">
          ${item.channels.map((channel) => `<span class="tag accent">${escapeHtml(channel)}</span>`).join("")}
          ${item.statuses.map((status) => `<span class="tag ${status === "answered" ? "ok" : status === "need_info" ? "warn" : "danger"}">${escapeHtml(statusLabel(status))}</span>`).join("")}
        </div>
      </article>
    `,
    "暂无热度数据。",
  );

  renderSimpleList(
    elements.unmatchedPool,
    dashboard?.unmatched_pool || [],
    (item) => `
      <article class="list-item">
        <div class="split-row">
          <h3>${escapeHtml(item.question)}</h3>
          <span class="tag danger">${escapeHtml(String(item.hits))} 次</span>
        </div>
        <p class="meta-copy">最近状态：${escapeHtml(statusLabel(item.last_status))} / 渠道：${escapeHtml(item.channel || "-")} / ${escapeHtml(formatTime(item.last_seen_at))}</p>
      </article>
    `,
    "暂无未命中问题。",
  );

  renderSimpleList(
    elements.staleDocs,
    dashboard?.stale_document_alerts || [],
    (item) => `
      <article class="list-item">
        <div class="split-row">
          <h3>${escapeHtml(item.file_name)}</h3>
          <span class="tag warn">${escapeHtml(String(item.hits))} 次</span>
        </div>
        <p class="meta-copy">最近命中：${escapeHtml(formatTime(item.last_seen_at))}</p>
      </article>
    `,
    "暂无过期资料命中。",
  );

  renderSimpleList(
    elements.aliasList,
    dashboard?.faq_aliases || [],
    (item) => `
      <article class="list-item">
        <div class="split-row">
          <h3>${escapeHtml(item.alias)}</h3>
          <span class="tag accent">${escapeHtml(item.faq_id)}</span>
        </div>
        <p class="meta-copy">${escapeHtml(item.faq_question)}</p>
        <p class="meta-copy">${escapeHtml(item.note || "无备注")}</p>
      </article>
    `,
    "暂无 FAQ 别名。",
  );

  renderSimpleList(
    elements.repairList,
    dashboard?.repair_items || [],
    (item) => `
      <article class="list-item">
        <div class="split-row">
          <h3>${escapeHtml(item.title)}</h3>
          <span class="tag accent">${escapeHtml(item.kind)}</span>
        </div>
        <p class="meta-copy">${escapeHtml(item.problem)}</p>
        <p class="meta-copy">建议：${escapeHtml(item.proposed_fix)}</p>
      </article>
    `,
    "暂无修复项。",
  );
}

function renderConversationDetail() {
  const summary = activeSummary();
  const detail = state.selectedConversation;
  elements.selectedConversationTip.textContent = state.selectedConversationId
    ? `修复项将关联会话 ${state.selectedConversationId.slice(0, 8)}`
    : "将自动关联当前选中的会话";

  if (!summary || !detail) {
    elements.detailTags.innerHTML = "";
    elements.conversationDetail.innerHTML = '<div class="empty-state">从左侧列表选择一个会话，即可查看来源渠道、接管状态和完整消息记录。</div>';
    return;
  }

  const latestAnswer = [...(detail.history || [])].reverse().find((item) => item.role === "assistant" && item.answer)?.answer || null;
  const messagesMarkup = (detail.history || [])
    .map(
      (item) => `
        <article class="timeline-entry ${item.role}">
          <div class="split-row">
            <h3>${escapeHtml(item.role === "assistant" ? "系统回复" : item.role === "user" ? "用户消息" : "系统提示")}</h3>
            <span class="timeline-time">${escapeHtml(formatTime(item.timestamp))}</span>
          </div>
          <p class="message-body">${escapeHtml(item.content)}</p>
        </article>
      `,
    )
    .join("");

  elements.detailTags.innerHTML = [
    `<span class="tag accent">${escapeHtml(conversationChannelLabel(summary))}</span>`,
    `<span class="tag ${summary.status === "handoff" ? "danger" : summary.status === "need_info" ? "warn" : "ok"}">${escapeHtml(statusLabel(summary.status))}</span>`,
    `<span class="tag warn">${escapeHtml(takeoverLabel(summary.takeover_status))}</span>`,
    summary.is_openclaw ? '<span class="tag accent">来自 OpenClaw</span>' : '<span class="tag accent">Web 会话</span>',
  ].join("");

  elements.conversationDetail.innerHTML = `
    <section class="detail-block">
      <p class="block-title">会话来源</p>
      <p class="message-body">渠道：${escapeHtml(summary.channel || "-")} / OpenClaw：${summary.is_openclaw ? "是" : "否"} / 来源会话：${escapeHtml(summary.source_session_id || "-")} / 目标：${escapeHtml(summary.source_target || "-")}</p>
    </section>
    <section class="detail-block">
      <p class="block-title">人工接管状态</p>
      <p class="message-body">状态：${escapeHtml(takeoverLabel(summary.takeover_status))} / 处理人：${escapeHtml(detail.takeover_by || summary.takeover_by || "-")}</p>
      <p class="message-body">备注：${escapeHtml(detail.takeover_note || "-")}</p>
    </section>
    <section class="detail-block full">
      <p class="block-title">当前画像</p>
      <p class="message-body">${escapeHtml(factsSummary(detail.remembered_facts || {}))}</p>
    </section>
    <section class="detail-block full">
      <div class="panel-head">
        <div>
          <p class="block-title">人工接管</p>
          <h3>将当前会话接管为人工</h3>
        </div>
      </div>
      <form id="takeoverForm" class="form-stack">
        <div class="form-stack two-col">
          <label>
            <span class="mini-label">处理人</span>
            <input name="agent_name" type="text" value="人工客服" />
          </label>
          <label>
            <span class="mini-label">接管状态</span>
            <select name="status">
              <option value="human">人工处理中</option>
              <option value="requested">待人工接管</option>
              <option value="resolved">已处理</option>
            </select>
          </label>
        </div>
        <label>
          <span class="mini-label">备注</span>
          <textarea name="note" rows="3" placeholder="记录人工接管原因、沟通要点或后续动作。"></textarea>
        </label>
        <button class="primary-button" type="submit">保存接管状态</button>
      </form>
    </section>
    <section class="detail-block full">
      <p class="block-title">最新系统结论</p>
      <p class="message-body">${escapeHtml(latestAnswer?.preliminary_judgement || latestAnswer?.conclusion || "暂无系统结论")}</p>
      <p class="meta-copy">可申报类别：${escapeHtml((latestAnswer?.reportable_categories || []).join(" / ") || "-")}</p>
    </section>
    <section class="detail-block full">
      <p class="block-title">消息历史</p>
      <div class="timeline-list">${messagesMarkup || '<div class="empty-state">暂无消息记录。</div>'}</div>
    </section>
  `;

  const takeoverForm = document.getElementById("takeoverForm");
  if (takeoverForm) {
    takeoverForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(takeoverForm);
      const payload = await adminPost(`/admin-api/conversations/${state.selectedConversationId}/takeover`, {
        agent_name: String(formData.get("agent_name") || "人工客服"),
        note: String(formData.get("note") || ""),
        status: String(formData.get("status") || "human"),
      });
      state.selectedConversation = payload;
      await refreshAll(false);
      showToast("人工接管状态已更新。");
    });
  }
}

async function fetchDashboard() {
  state.dashboard = await adminGet("/admin-api/dashboard");
}

async function fetchConversations() {
  const payload = await adminGet("/admin-api/conversations");
  state.conversations = payload.items || [];
  if (!state.selectedConversationId && state.conversations.length) {
    state.selectedConversationId = state.conversations[0].conversation_id;
  }
}

async function loadConversation(conversationId) {
  if (!conversationId) {
    return;
  }
  state.selectedConversationId = conversationId;
  state.selectedConversation = await adminGet(`/admin-api/conversations/${conversationId}`);
}

async function refreshAll(keepSelection = true) {
  const previousId = keepSelection ? state.selectedConversationId : null;
  await Promise.all([fetchDashboard(), fetchConversations()]);
  if (previousId) {
    state.selectedConversationId = previousId;
  }
  if (state.selectedConversationId) {
    try {
      await loadConversation(state.selectedConversationId);
    } catch {
      state.selectedConversation = null;
    }
  }
  renderMetrics();
  renderTakeoverQueue();
  renderConversations();
  renderDashboardLists();
  renderConversationDetail();
}

function bindEvents() {
  elements.adminLoginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = elements.adminUsername.value.trim();
    const password = elements.adminPassword.value;
    if (!username || !password) {
      return;
    }
    try {
      elements.adminLoginSubmit.disabled = true;
      const session = await adminLogin(username, password);
      applyAdminSession(session);
      await refreshAll(true);
      showToast("已登录后台。");
    } catch (error) {
      showToast(error.message || String(error));
      elements.adminLoginHint.textContent = "登录失败，请检查用户名和密码。";
    } finally {
      elements.adminLoginSubmit.disabled = !state.adminSession.login_enabled;
      elements.adminPassword.value = "";
    }
  });

  elements.adminLogoutBtn?.addEventListener("click", async () => {
    try {
      const session = await adminLogout();
      applyAdminSession(session);
      clearWorkspace();
      showToast("已退出后台。");
    } catch (error) {
      showToast(error.message || String(error));
    }
  });

  elements.refreshDashboardBtn.addEventListener("click", async () => {
    await refreshAll(true);
    showToast("后台看板已刷新。");
  });

  elements.adminWorkspaceTabs?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab]");
    if (!button) {
      return;
    }
    setActiveTab(button.dataset.tab);
  });

  const handleConversationClick = async (event) => {
    const button = event.target.closest("[data-conversation-id]");
    if (!button) {
      return;
    }
    setActiveTab("conversations");
    await loadConversation(button.dataset.conversationId);
    renderTakeoverQueue();
    renderConversations();
    renderConversationDetail();
  };
  elements.conversationList.addEventListener("click", handleConversationClick);
  elements.takeoverQueue.addEventListener("click", handleConversationClick);

  elements.aliasForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(elements.aliasForm);
    await adminPost("/admin-api/faq-aliases", {
      alias: String(formData.get("alias") || ""),
      faq_id: String(formData.get("faq_id") || ""),
      faq_question: String(formData.get("faq_question") || ""),
      note: String(formData.get("note") || ""),
    });
    elements.aliasForm.reset();
    await refreshAll(true);
    showToast("FAQ 别名已保存。");
  });

  elements.repairForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(elements.repairForm);
    const summary = activeSummary();
    const latestAnswer = [...(state.selectedConversation?.history || [])].reverse().find((item) => item.role === "assistant" && item.answer)?.answer || null;
    await adminPost("/admin-api/repair-items", {
      conversation_id: state.selectedConversationId,
      kind: String(formData.get("kind") || "manual"),
      title: String(formData.get("title") || ""),
      problem: String(formData.get("problem") || ""),
      manual_reply: String(formData.get("manual_reply") || ""),
      proposed_fix: String(formData.get("proposed_fix") || ""),
      source_channel: summary?.channel || "web",
      create_alias: String(formData.get("create_alias") || "") || null,
      alias_faq_id: latestAnswer?.matched_faq_ids?.[0] || null,
      alias_faq_question: summary?.title || null,
      alias_note: String(formData.get("alias_note") || ""),
    });
    elements.repairForm.reset();
    await refreshAll(true);
    showToast("修复项已沉淀。");
  });
}

async function bootstrap() {
  bindEvents();
  renderWorkspaceTabs();
  const session = await fetchAdminSession();
  applyAdminSession(session);
  if (!state.adminSession.authenticated) {
    clearWorkspace();
    return;
  }
  await refreshAll(true);
}

bootstrap().catch((error) => {
  console.error(error);
  showToast("后台初始化失败，请刷新后重试。");
});

export const STATUS_LABELS = {
  answered: "可回答",
  need_info: "待补充",
  handoff: "转人工",
  out_of_scope: "超范围",
};

export const TAKEOVER_LABELS = {
  bot: "机器人跟进",
  requested: "待人工接管",
  human: "人工处理中",
  resolved: "已处理",
};

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function statusLabel(status) {
  return STATUS_LABELS[status] || status || "未知";
}

export function takeoverLabel(status) {
  return TAKEOVER_LABELS[status] || status || "未接管";
}

export function formatTime(value) {
  if (!value) {
    return "-";
  }
  try {
    return new Date(value).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return value;
  }
}

export function boolText(value) {
  if (value === true) {
    return "是";
  }
  if (value === false) {
    return "否";
  }
  return "未填写";
}

export function factsSummary(facts) {
  const items = [];
  if (facts.stage) items.push(`学段：${facts.stage}`);
  if (facts.child_hukou) items.push(`学童户籍：${facts.child_hukou}`);
  if (facts.parent_hukou) items.push(`监护人户籍：${facts.parent_hukou}`);
  if (facts.parent_work_in_songshanhu !== null && facts.parent_work_in_songshanhu !== undefined) {
    items.push(`工作地：${facts.parent_work_in_songshanhu ? "松山湖" : "非松山湖"}`);
  }
  if (facts.has_songshanhu_property !== null && facts.has_songshanhu_property !== undefined) {
    items.push(`松山湖房产：${facts.has_songshanhu_property ? "有" : "无"}`);
  }
  if (facts.property_owner) items.push(`产权：${facts.property_owner}`);
  if (Array.isArray(facts.special_status) && facts.special_status.length) {
    items.push(`优待身份：${facts.special_status.join("、")}`);
  }
  if (facts.employer_type) items.push(`单位信息：${facts.employer_type}`);
  if (facts.is_transfer !== null && facts.is_transfer !== undefined) {
    items.push(`是否转学：${facts.is_transfer ? "是" : "否"}`);
  }
  return items.length ? items.join(" / ") : "当前会话还没有形成完整画像。";
}

export function compactPreview(value, limit = 92) {
  const source = String(value ?? "")
    .replace(/【[^】]+】/g, " ")
    .replace(/(初步结论：|可申报类别 \/ 当前问题判断：|建议信息：|判断依据：|资料来源：|人工协助方式：)/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!source) {
    return "";
  }
  if (source.length <= limit) {
    return source;
  }
  return `${source.slice(0, limit - 1).trimEnd()}…`;
}

export function conversationChannelLabel(item) {
  if (item.is_openclaw) {
    return `OpenClaw / ${item.channel || "未知渠道"}`;
  }
  return item.channel === "web" ? "Web 前台" : item.channel || "其他渠道";
}

export async function apiGet(url) {
  const response = await fetch(url, {
    credentials: "same-origin",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

export async function apiPost(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
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

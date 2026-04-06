-- PostgreSQL skeleton schema for the Songshan Lake admissions consultation system.
-- This file is intentionally conservative: it establishes traceability and routing
-- first, and leaves detailed indexing and vector storage decisions for later.

create table if not exists knowledge_source (
  source_id text primary key,
  title text not null,
  relative_path text not null,
  source_type text not null,
  policy_level text,
  source_tier integer not null default 99,
  published_at timestamptz,
  effective_from date,
  effective_to date,
  freshness_status text not null default 'unknown',
  content_hash text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists knowledge_chunk (
  chunk_id text primary key,
  source_id text not null references knowledge_source(source_id),
  title text not null,
  page_no integer,
  chunk_index integer not null,
  text_content text not null,
  token_count integer,
  embedding_ref text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_knowledge_chunk_source on knowledge_chunk(source_id);

create table if not exists faq_entry (
  faq_id text primary key,
  source_id text not null references knowledge_source(source_id),
  question text not null,
  answer text not null,
  category_code text,
  tags text[] not null default '{}',
  is_active boolean not null default true,
  version_tag text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists rule_set (
  rule_set_id text primary key,
  name text not null,
  version text not null,
  policy_year integer,
  status text not null default 'draft',
  priority integer not null default 100,
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists rule_clause (
  clause_id text primary key,
  rule_set_id text not null references rule_set(rule_set_id),
  category_code text,
  intent text,
  predicate_json jsonb not null,
  outcome_json jsonb not null,
  requires_manual_review boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists agent_profile (
  agent_profile_id text primary key,
  name text not null,
  mode text not null,
  prompt_bundle text not null,
  knowledge_scope jsonb not null default '[]'::jsonb,
  rule_scope jsonb not null default '[]'::jsonb,
  fallback_template text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists channel_binding (
  binding_id text primary key,
  channel text not null,
  scope text not null,
  peer_id text,
  group_id text,
  require_mention boolean not null default false,
  pairing_mode text not null default 'disabled',
  allowlist jsonb not null default '[]'::jsonb,
  agent_profile_id text not null references agent_profile(agent_profile_id),
  fallback_agent_profile_id text references agent_profile(agent_profile_id),
  enabled boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists consultation_session (
  session_id text primary key,
  external_conversation_id text,
  channel text not null,
  conversation_mode text not null,
  agent_profile_id text not null references agent_profile(agent_profile_id),
  case_id text,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists consultation_message (
  message_id text primary key,
  session_id text not null references consultation_session(session_id),
  direction text not null,
  sender_role text not null,
  normalized_payload jsonb not null,
  text_content text not null,
  raw_payload_ref text,
  received_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_consultation_message_session on consultation_message(session_id);

create table if not exists case_profile (
  case_id text primary key,
  session_id text not null references consultation_session(session_id),
  audience_type text not null,
  requested_school_year integer,
  requested_stage text,
  facts jsonb not null default '{}'::jsonb,
  missing_fields text[] not null default '{}',
  pii_redacted_summary text,
  status text not null default 'open',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists classification_run (
  run_id text primary key,
  case_id text not null references case_profile(case_id),
  intent text not null,
  category_code text not null,
  confidence numeric(4, 3) not null,
  freshness_status text not null default 'unknown',
  manual_review_required boolean not null default false,
  requires_clarification boolean not null default false,
  missing_fields text[] not null default '{}',
  disqualifiers text[] not null default '{}',
  rule_hits jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists answer_trace (
  answer_id text primary key,
  run_id text not null references classification_run(run_id),
  session_id text not null references consultation_session(session_id),
  status text not null,
  answer_payload jsonb not null,
  evidence_refs jsonb not null default '[]'::jsonb,
  rendered_text text,
  created_at timestamptz not null default now()
);

create table if not exists escalation_ticket (
  ticket_id text primary key,
  session_id text not null references consultation_session(session_id),
  case_id text not null references case_profile(case_id),
  run_id text references classification_run(run_id),
  queue_name text not null,
  reason_codes text[] not null default '{}',
  handoff_summary text not null,
  status text not null default 'open',
  assigned_to text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists feedback_event (
  feedback_id text primary key,
  session_id text not null references consultation_session(session_id),
  answer_id text references answer_trace(answer_id),
  rating integer,
  issue_type text,
  note text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists source_refresh_alert (
  alert_id text primary key,
  source_id text references knowledge_source(source_id),
  alert_type text not null,
  detail text not null,
  status text not null default 'open',
  detected_at timestamptz not null default now(),
  resolved_at timestamptz
);

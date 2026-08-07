-- Durable automation state used by deterministic workers and Codex fallbacks.

alter table source_items
  add column if not exists fetched_at timestamptz,
  add column if not exists evaluated_at timestamptz,
  add column if not exists emailed_at timestamptz,
  add column if not exists db_synced_at timestamptz,
  add column if not exists processing_status text,
  add column if not exists processing_error text;

create index if not exists source_items_processing_idx
  on source_items(provider_id, source_type, evaluated_at, emailed_at, db_synced_at);

create table if not exists email_notifications (
  id uuid primary key default gen_random_uuid(),
  provider_id uuid references providers(id) on delete set null,
  automation_run_id uuid references automation_runs(id) on delete set null,
  idempotency_key text not null unique,
  to_address text not null,
  subject text not null,
  status text not null default 'pending',
  attempts integer not null default 0,
  sent_at timestamptz,
  last_error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists email_notifications_provider_id_idx
  on email_notifications(provider_id);

create index if not exists email_notifications_run_id_idx
  on email_notifications(automation_run_id);

create index if not exists email_notifications_status_idx
  on email_notifications(status, created_at);

create table if not exists automation_run_events (
  id uuid primary key default gen_random_uuid(),
  provider_id uuid references providers(id) on delete set null,
  automation_run_id uuid references automation_runs(id) on delete set null,
  run_key text,
  event_type text not null,
  severity text not null default 'info',
  message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists automation_run_events_run_key_idx
  on automation_run_events(run_key, created_at);

create index if not exists automation_run_events_provider_id_idx
  on automation_run_events(provider_id);

alter table email_notifications enable row level security;
alter table automation_run_events enable row level security;

create policy "email_notifications_crm" on email_notifications
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "automation_run_events_crm" on automation_run_events
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

drop trigger if exists set_email_notifications_updated_at on email_notifications;
create trigger set_email_notifications_updated_at
  before update on email_notifications
  for each row execute function set_updated_at();

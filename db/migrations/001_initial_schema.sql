-- Supabase job tracking schema.
-- Private, script-driven v1: no RLS policies are enabled here.

create extension if not exists pgcrypto;

create table if not exists jobtracker_schema_migrations (
  version text primary key,
  applied_at timestamptz not null default now()
);

create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists providers (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  provider_type text not null default 'job_board',
  website_url text,
  notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  normalized_name text not null unique,
  website_url text,
  domains text[] not null default '{}',
  industry text,
  location_text text,
  notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists opportunities (
  id uuid primary key default gen_random_uuid(),
  provider_id uuid references providers(id) on delete set null,
  organization_id uuid references organizations(id) on delete set null,
  opportunity_type text not null default 'employment',
  title text not null,
  normalized_title text,
  external_id text,
  source_url text,
  apply_url text,
  location_text text,
  work_model text,
  engagement_type text,
  seniority text,
  domain text,
  compensation_text text,
  compensation_min numeric,
  compensation_max numeric,
  compensation_currency text,
  budget_type text,
  source_status text,
  first_seen_at timestamptz,
  last_seen_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists opportunities_provider_external_id_uidx
  on opportunities(provider_id, external_id)
  where external_id is not null;

create index if not exists opportunities_dedupe_idx
  on opportunities(provider_id, organization_id, normalized_title, location_text);

create index if not exists opportunities_metadata_gin
  on opportunities using gin(metadata);

create table if not exists artifacts (
  id uuid primary key default gen_random_uuid(),
  artifact_type text not null,
  title text,
  storage_bucket text,
  storage_path text,
  local_path text,
  mime_type text,
  sha256 text,
  size_bytes bigint,
  related_type text,
  related_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists automation_runs (
  id uuid primary key default gen_random_uuid(),
  provider_id uuid references providers(id) on delete set null,
  run_key text unique,
  started_at timestamptz,
  finished_at timestamptz,
  status text not null default 'completed',
  report_artifact_id uuid references artifacts(id) on delete set null,
  report_email_sent boolean,
  report_email_subject text,
  source_items_count integer not null default 0,
  opportunities_count integer not null default 0,
  evaluations_count integer not null default 0,
  manual_review_count integer not null default 0,
  summary text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists source_items (
  id uuid primary key default gen_random_uuid(),
  provider_id uuid references providers(id) on delete set null,
  opportunity_id uuid references opportunities(id) on delete set null,
  automation_run_id uuid references automation_runs(id) on delete set null,
  artifact_id uuid references artifacts(id) on delete set null,
  source_type text not null,
  external_id text,
  source_url text,
  source_timestamp timestamptz,
  title text,
  summary text,
  raw_text text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists source_items_provider_external_uidx
  on source_items(provider_id, source_type, external_id)
  where external_id is not null;

create table if not exists evaluations (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid references opportunities(id) on delete cascade,
  automation_run_id uuid references automation_runs(id) on delete set null,
  provider_id uuid references providers(id) on delete set null,
  score numeric,
  confidence text,
  recommendation text,
  priority text,
  verdict text,
  main_match text,
  main_risks text,
  missing_information text,
  positioning_angle text,
  salary_expectation text,
  pricing_recommendation text,
  proposal_text text,
  action_next text,
  manual_review_reason text,
  evaluated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists applications (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid references opportunities(id) on delete set null,
  organization_id uuid references organizations(id) on delete set null,
  provider_id uuid references providers(id) on delete set null,
  application_channel text,
  status text not null default 'applied',
  current_stage text,
  applied_at date,
  salary_requested_text text,
  salary_requested_min numeric,
  salary_requested_max numeric,
  salary_requested_currency text,
  outcome text,
  decline_reason text,
  passed boolean,
  notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists applications_status_idx on applications(status);
create index if not exists applications_applied_at_idx on applications(applied_at);

create table if not exists application_events (
  id uuid primary key default gen_random_uuid(),
  application_id uuid references applications(id) on delete cascade,
  event_type text not null,
  event_at timestamptz,
  title text,
  description text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists contacts (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references organizations(id) on delete set null,
  full_name text,
  role_title text,
  email text,
  linkedin_url text,
  notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists interviews (
  id uuid primary key default gen_random_uuid(),
  application_id uuid references applications(id) on delete cascade,
  organization_id uuid references organizations(id) on delete set null,
  stage text,
  scheduled_at timestamptz,
  completed_at timestamptz,
  meeting_url text,
  result text,
  feedback_summary text,
  transcript_artifact_id uuid references artifacts(id) on delete set null,
  notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists interview_contacts (
  interview_id uuid references interviews(id) on delete cascade,
  contact_id uuid references contacts(id) on delete cascade,
  role_in_interview text,
  primary key(interview_id, contact_id)
);

create table if not exists communications (
  id uuid primary key default gen_random_uuid(),
  application_id uuid references applications(id) on delete set null,
  organization_id uuid references organizations(id) on delete set null,
  contact_id uuid references contacts(id) on delete set null,
  artifact_id uuid references artifacts(id) on delete set null,
  direction text,
  channel text,
  subject text,
  sent_at timestamptz,
  summary text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists insights (
  id uuid primary key default gen_random_uuid(),
  insight_type text not null,
  title text not null,
  body text,
  related_type text,
  related_id uuid,
  confidence text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists legacy_import_rows (
  id uuid primary key default gen_random_uuid(),
  source_file text not null,
  row_number integer not null,
  stable_key text not null,
  fallback_key text not null,
  raw_row jsonb not null,
  original_link_text text,
  provider_id uuid references providers(id) on delete set null,
  organization_id uuid references organizations(id) on delete set null,
  opportunity_id uuid references opportunities(id) on delete set null,
  application_id uuid references applications(id) on delete set null,
  source_item_id uuid references source_items(id) on delete set null,
  import_warnings text[] not null default '{}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(source_file, row_number)
);

create unique index if not exists legacy_import_rows_fallback_uidx
  on legacy_import_rows(source_file, fallback_key);

create table if not exists document_chunks (
  id uuid primary key default gen_random_uuid(),
  artifact_id uuid references artifacts(id) on delete cascade,
  related_type text,
  related_id uuid,
  chunk_index integer not null default 0,
  content text not null,
  content_tsv tsvector generated always as (to_tsvector('english', coalesce(content, ''))) stored,
  embedding real[],
  embedding_model text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists document_chunks_tsv_idx
  on document_chunks using gin(content_tsv);

create index if not exists document_chunks_metadata_gin
  on document_chunks using gin(metadata);

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'providers', 'organizations', 'opportunities', 'automation_runs',
    'source_items', 'evaluations', 'applications', 'contacts',
    'interviews', 'communications', 'insights', 'legacy_import_rows'
  ]
  loop
    execute format('drop trigger if exists set_%I_updated_at on %I', table_name, table_name);
    execute format(
      'create trigger set_%I_updated_at before update on %I for each row execute function set_updated_at()',
      table_name,
      table_name
    );
  end loop;
end;
$$;

insert into providers(slug, name, provider_type, website_url)
values
  ('linkedin', 'LinkedIn', 'job_board', 'https://www.linkedin.com/jobs/'),
  ('upwork', 'Upwork', 'freelance_marketplace', 'https://www.upwork.com/'),
  ('greenhouse', 'Greenhouse', 'ats', 'https://www.greenhouse.com/'),
  ('djinni', 'Djinni', 'job_board', 'https://djinni.co/'),
  ('dou', 'DOU', 'job_board', 'https://jobs.dou.ua/'),
  ('workua', 'Work.ua', 'job_board', 'https://www.work.ua/'),
  ('freelancehunt', 'FreelanceHunt', 'freelance_marketplace', 'https://freelancehunt.com/'),
  ('manual_import', 'Manual import', 'manual', null),
  ('legacy_csv', 'Legacy CSV', 'manual', null)
on conflict(slug) do update set
  name = excluded.name,
  provider_type = excluded.provider_type,
  website_url = excluded.website_url,
  updated_at = now();


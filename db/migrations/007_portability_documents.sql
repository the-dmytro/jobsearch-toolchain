-- Portable continuity: documents, retained job texts, compact opportunity cards.
-- Non-destructive: existing rows and metadata are kept. Use `jobtracker compact-db`
-- to remove legacy full-payload copies after verification.

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  kind text not null,
  status text not null default 'draft',
  title text,
  body text not null,
  content_format text not null default 'markdown',
  content_sha256 text not null,
  source_key text,
  base_profile_sha text,
  created_by text,
  opportunity_id uuid references opportunities(id) on delete set null,
  application_id uuid references applications(id) on delete set null,
  organization_id uuid references organizations(id) on delete set null,
  automation_run_id uuid references automation_runs(id) on delete set null,
  parent_id uuid references documents(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint documents_status_check check (status in ('draft', 'final', 'sent', 'discarded', 'archived'))
);

create unique index if not exists documents_source_key_uidx
  on documents(source_key) where source_key is not null;
create index if not exists documents_kind_status_idx on documents(kind, status);
create index if not exists documents_opportunity_id_idx on documents(opportunity_id);
create index if not exists documents_application_id_idx on documents(application_id);
create index if not exists documents_organization_id_idx on documents(organization_id);
create index if not exists documents_automation_run_id_idx on documents(automation_run_id);
create index if not exists documents_parent_id_idx on documents(parent_id);
create index if not exists documents_content_sha256_idx on documents(content_sha256);

create table if not exists opportunity_texts (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references opportunities(id) on delete cascade,
  content_sha256 text not null,
  language text,
  body text not null,
  retention_reason text,
  source_item_external_id text,
  fetched_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (opportunity_id, content_sha256)
);

alter table opportunities
  add column if not exists description_sha256 text,
  add column if not exists description_excerpt text,
  add column if not exists external_id_aliases text[] not null default '{}',
  add column if not exists requirement_tags text[] not null default '{}';

create index if not exists opportunities_description_sha256_idx on opportunities(description_sha256);
create index if not exists opportunities_external_id_aliases_gin on opportunities using gin(external_id_aliases);
create index if not exists opportunities_requirement_tags_gin on opportunities using gin(requirement_tags);

alter table source_items add column if not exists body_sha256 text;

-- One application per opportunity; replays update instead of inserting duplicates.
create index if not exists applications_opportunity_id_idx on applications(opportunity_id);

drop trigger if exists set_documents_updated_at on documents;
create trigger set_documents_updated_at before update on documents
  for each row execute function set_updated_at();

alter table documents enable row level security;
alter table opportunity_texts enable row level security;

do $$
begin
  if exists (select 1 from pg_proc where proname = 'crm_is_owner') then
    execute 'drop policy if exists "documents_crm" on documents';
    execute 'create policy "documents_crm" on documents for all to authenticated using (public.crm_is_owner()) with check (public.crm_is_owner())';
    execute 'drop policy if exists "opportunity_texts_crm" on opportunity_texts';
    execute 'create policy "opportunity_texts_crm" on opportunity_texts for all to authenticated using (public.crm_is_owner()) with check (public.crm_is_owner())';
  end if;
end;
$$;

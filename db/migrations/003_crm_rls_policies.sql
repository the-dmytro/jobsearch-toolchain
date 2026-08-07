-- CRM: single-user RLS for Supabase Auth (anon key) + job-artifacts storage read.
-- Service role and direct Postgres (Python jobtracker) bypass RLS.

create table if not exists crm_owner_allowlist (
  email text primary key
);

-- Seed owner email via env after migrate, e.g.:
-- insert into crm_owner_allowlist (email) values ('<CRM_OWNER_EMAIL>') on conflict do nothing;

-- Allowlist is not RLS-protected; lock down to read-only for clients
revoke all on crm_owner_allowlist from public;
grant select on crm_owner_allowlist to authenticated, anon;

create or replace function public.crm_is_owner()
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select exists (
    select 1
    from crm_owner_allowlist a
    where a.email = coalesce((select auth.jwt() ->> 'email'), '')
  );
$$;

-- -------- domain table policies (authenticated only) --------

create policy "providers_crm" on providers
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "organizations_crm" on organizations
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "opportunities_crm" on opportunities
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "artifacts_crm" on artifacts
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "automation_runs_crm" on automation_runs
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "source_items_crm" on source_items
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "evaluations_crm" on evaluations
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "applications_crm" on applications
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "application_events_crm" on application_events
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "contacts_crm" on contacts
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "interviews_crm" on interviews
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "interview_contacts_crm" on interview_contacts
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "communications_crm" on communications
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "insights_crm" on insights
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "document_chunks_crm" on document_chunks
  for all to authenticated
  using (public.crm_is_owner())
  with check (public.crm_is_owner());

create policy "legacy_import_rows_select_crm" on legacy_import_rows
  for select to authenticated
  using (public.crm_is_owner());

-- -------- Storage: job-artifacts bucket --------

drop policy if exists "job-artifacts authenticated read" on storage.objects;
create policy "job-artifacts authenticated read"
  on storage.objects
  for select
  to authenticated
  using (
    bucket_id = 'job-artifacts'
    and public.crm_is_owner()
  );

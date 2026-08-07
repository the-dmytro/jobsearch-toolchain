-- Harden public-schema access for private, script-driven job tracking data.
-- Service-role and direct Postgres automation still work; anon/authenticated REST
-- access has no table policies by default.

create or replace function set_updated_at()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

alter table jobtracker_schema_migrations enable row level security;
alter table providers enable row level security;
alter table organizations enable row level security;
alter table opportunities enable row level security;
alter table artifacts enable row level security;
alter table automation_runs enable row level security;
alter table source_items enable row level security;
alter table evaluations enable row level security;
alter table applications enable row level security;
alter table application_events enable row level security;
alter table contacts enable row level security;
alter table interviews enable row level security;
alter table interview_contacts enable row level security;
alter table communications enable row level security;
alter table insights enable row level security;
alter table legacy_import_rows enable row level security;
alter table document_chunks enable row level security;

create index if not exists opportunities_organization_id_idx on opportunities(organization_id);
create index if not exists applications_opportunity_id_idx on applications(opportunity_id);
create index if not exists applications_organization_id_idx on applications(organization_id);
create index if not exists applications_provider_id_idx on applications(provider_id);
create index if not exists application_events_application_id_idx on application_events(application_id);
create index if not exists automation_runs_provider_id_idx on automation_runs(provider_id);
create index if not exists automation_runs_report_artifact_id_idx on automation_runs(report_artifact_id);
create index if not exists source_items_opportunity_id_idx on source_items(opportunity_id);
create index if not exists source_items_automation_run_id_idx on source_items(automation_run_id);
create index if not exists source_items_artifact_id_idx on source_items(artifact_id);
create index if not exists contacts_organization_id_idx on contacts(organization_id);
create index if not exists interviews_application_id_idx on interviews(application_id);
create index if not exists interviews_organization_id_idx on interviews(organization_id);
create index if not exists interviews_transcript_artifact_id_idx on interviews(transcript_artifact_id);
create index if not exists interview_contacts_contact_id_idx on interview_contacts(contact_id);
create index if not exists communications_application_id_idx on communications(application_id);
create index if not exists communications_organization_id_idx on communications(organization_id);
create index if not exists communications_contact_id_idx on communications(contact_id);
create index if not exists communications_artifact_id_idx on communications(artifact_id);
create index if not exists evaluations_opportunity_id_idx on evaluations(opportunity_id);
create index if not exists evaluations_automation_run_id_idx on evaluations(automation_run_id);
create index if not exists evaluations_provider_id_idx on evaluations(provider_id);
create index if not exists legacy_import_rows_provider_id_idx on legacy_import_rows(provider_id);
create index if not exists legacy_import_rows_organization_id_idx on legacy_import_rows(organization_id);
create index if not exists legacy_import_rows_opportunity_id_idx on legacy_import_rows(opportunity_id);
create index if not exists legacy_import_rows_application_id_idx on legacy_import_rows(application_id);
create index if not exists legacy_import_rows_source_item_id_idx on legacy_import_rows(source_item_id);
create index if not exists document_chunks_artifact_id_idx on document_chunks(artifact_id);

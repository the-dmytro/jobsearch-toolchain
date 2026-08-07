-- Close the owner-gate bypass: crm_owner_allowlist must not be reachable via PostgREST.
-- Publishable/anon keys stay public; security is enforced in Postgres (RLS + grants).
-- service_role and direct Postgres (jobtracker) are unchanged.

alter table crm_owner_allowlist enable row level security;

revoke all on table crm_owner_allowlist from anon, authenticated, public;

revoke execute on function public.crm_is_owner() from public, anon;
grant execute on function public.crm_is_owner() to authenticated;

-- HTTPS SQL gateway for environments that only allow HTTP(S) egress (for example
-- cloud agent sandboxes). The toolchain's `store.transport = "supabase_https"` sends
-- each statement to POST /rest/v1/rpc/jobtracker_sql with the project's secret key.
--
-- Only service_role may execute it. The secret key already has full data access
-- through the Data API; this function adds the ability to run the toolchain's own
-- statements, including later migrations. It runs as its owner (SECURITY DEFINER)
-- because Supabase tables belong to `postgres`, so DDL needs the owner's rights.
-- Never grant it to anon or authenticated.

create or replace function public.jobtracker_sql(query text, mode text default 'rows')
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  result jsonb;
  affected bigint;
begin
  if mode = 'rows' then
    execute format('with _jobtracker_result as (%s) select coalesce(jsonb_agg(to_jsonb(_jobtracker_result)), ''[]''::jsonb) from _jobtracker_result', query)
      into result;
    return jsonb_build_object('rows', result, 'rowcount', jsonb_array_length(result));
  elsif mode = 'exec' then
    execute query;
    get diagnostics affected = row_count;
    return jsonb_build_object('rows', '[]'::jsonb, 'rowcount', affected);
  end if;
  raise exception 'jobtracker_sql: unsupported mode %', mode;
end;
$$;

revoke all on function public.jobtracker_sql(text, text) from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on function public.jobtracker_sql(text, text) from anon';
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'revoke all on function public.jobtracker_sql(text, text) from authenticated';
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    execute 'grant execute on function public.jobtracker_sql(text, text) to service_role';
  end if;
end;
$$;

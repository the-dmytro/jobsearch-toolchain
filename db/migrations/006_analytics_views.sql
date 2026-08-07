-- Read-only analytics views for the CRM dashboard.
-- security_invoker ensures underlying RLS (crm_is_owner) still applies.

create or replace view public.v_funnel_summary
with (security_invoker = true)
as
with counts as (
  select
    (select count(*)::bigint from public.opportunities) as opportunities_count,
    (select count(distinct opportunity_id)::bigint from public.evaluations) as evaluated_count,
    (select count(*)::bigint from public.applications) as applied_count,
    (
      select count(*)::bigint
      from public.applications a
      where lower(coalesce(a.current_stage, '')) in (
        'screening', 'tech_interview', 'onsite', 'phone', 'technical', 'intro', 'recruiter'
      )
        or lower(coalesce(a.current_stage, '')) like '%interview%'
    ) as interviewing_count,
    (
      select count(*)::bigint
      from public.applications a
      where lower(coalesce(a.current_stage, '')) like '%offer%'
        or lower(coalesce(a.outcome, '')) like '%offer%'
    ) as offer_count
)
select
  opportunities_count,
  evaluated_count,
  applied_count,
  interviewing_count,
  offer_count,
  case
    when opportunities_count > 0
    then round(evaluated_count::numeric / opportunities_count * 100, 1)
    else 0
  end as opp_to_eval_pct,
  case
    when evaluated_count > 0
    then round(applied_count::numeric / evaluated_count * 100, 1)
    else 0
  end as eval_to_applied_pct,
  case
    when applied_count > 0
    then round(interviewing_count::numeric / applied_count * 100, 1)
    else 0
  end as applied_to_interview_pct,
  case
    when interviewing_count > 0
    then round(offer_count::numeric / interviewing_count * 100, 1)
    else 0
  end as interview_to_offer_pct
from counts;

create or replace view public.v_weekly_activity
with (security_invoker = true)
as
select
  date_trunc('week', activity_at)::date as week_start,
  count(*) filter (where activity_type = 'opportunity') as opportunities,
  count(*) filter (where activity_type = 'application') as applications,
  count(*) filter (where activity_type = 'interview') as interviews
from (
  select created_at as activity_at, 'opportunity' as activity_type
  from public.opportunities
  union all
  select coalesce(applied_at::timestamptz, created_at), 'application'
  from public.applications
  union all
  select coalesce(scheduled_at, completed_at, created_at), 'interview'
  from public.interviews
) activity
group by 1
order by 1;

create or replace view public.v_response_latency
with (security_invoker = true)
as
with first_responses as (
  select
    a.id as application_id,
    a.applied_at,
    min(ae.event_at) as first_response_at
  from public.applications a
  join public.application_events ae on ae.application_id = a.id
  where a.applied_at is not null
    and ae.event_at is not null
    and lower(ae.event_type) in ('reply', 'interview_invite', 'response')
  group by a.id, a.applied_at
)
select
  application_id,
  applied_at,
  first_response_at,
  greatest(
    0,
    extract(day from (first_response_at - applied_at::timestamptz))
  )::integer as latency_days
from first_responses;

create or replace view public.v_source_effectiveness
with (security_invoker = true)
as
select
  p.id as provider_id,
  p.slug as provider_slug,
  p.name as provider_name,
  count(distinct o.id)::bigint as opportunities,
  count(distinct a.id)::bigint as applications,
  count(distinct i.id)::bigint as interviews,
  count(distinct a.id) filter (
    where lower(coalesce(a.current_stage, '')) like '%offer%'
      or lower(coalesce(a.outcome, '')) like '%offer%'
  )::bigint as offers,
  case
    when count(distinct a.id) > 0
    then round(
      count(distinct i.id)::numeric / count(distinct a.id) * 100,
      1
    )
    else 0
  end as app_to_interview_pct
from public.providers p
left join public.opportunities o on o.provider_id = p.id
left join public.applications a on a.provider_id = p.id
left join public.interviews i on i.application_id = a.id
group by p.id, p.slug, p.name
order by applications desc, opportunities desc;

create or replace view public.v_pipeline_aging
with (security_invoker = true)
as
select
  a.id as application_id,
  coalesce(org.name, 'Unknown company') as organization_name,
  coalesce(o.title, 'Untitled role') as opportunity_title,
  a.current_stage,
  a.status,
  greatest(
    0,
    extract(day from (now() - coalesce(a.updated_at, a.created_at)))
  )::integer as days_in_stage,
  a.applied_at,
  a.updated_at
from public.applications a
left join public.opportunities o on o.id = a.opportunity_id
left join public.organizations org on org.id = coalesce(a.organization_id, o.organization_id)
where lower(coalesce(a.status, 'active')) not in ('declined', 'rejected', 'withdrawn', 'closed')
  and lower(coalesce(a.outcome, '')) not in ('declined', 'rejected', 'withdrawn')
  and lower(coalesce(a.current_stage, '')) not in ('declined', 'rejected', 'withdrawn');

create or replace view public.v_score_outcomes
with (security_invoker = true)
as
select
  case
    when e.score is null then 'unknown'
    when e.score < 3 then '0-2'
    when e.score < 5 then '3-4'
    when e.score < 7 then '5-6'
    when e.score < 9 then '7-8'
    else '9-10'
  end as score_bucket,
  count(*)::bigint as evaluation_count,
  count(*) filter (
    where lower(coalesce(a.outcome, '')) like '%offer%'
      or lower(coalesce(a.current_stage, '')) like '%offer%'
  )::bigint as offer_count,
  count(*) filter (
    where a.outcome is not null and a.outcome <> ''
  )::bigint as resolved_count,
  round(avg(e.score)::numeric, 2) as avg_score
from public.evaluations e
left join public.applications a on a.opportunity_id = e.opportunity_id
group by 1
order by
  case score_bucket
    when '0-2' then 1
    when '3-4' then 2
    when '5-6' then 3
    when '7-8' then 4
    when '9-10' then 5
    else 6
  end;

grant select on public.v_funnel_summary to authenticated;
grant select on public.v_weekly_activity to authenticated;
grant select on public.v_response_latency to authenticated;
grant select on public.v_source_effectiveness to authenticated;
grant select on public.v_pipeline_aging to authenticated;
grant select on public.v_score_outcomes to authenticated;

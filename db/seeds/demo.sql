-- Synthetic demo dataset for CRM dashboard screenshots and local evaluation.
-- No personal data. Safe to run multiple times (uses deterministic UUIDs).

insert into public.providers (id, slug, name, provider_type, website_url)
values
  ('11111111-1111-4111-8111-111111111101', 'greenhouse', 'Greenhouse Board', 'ats', 'https://example.com/greenhouse'),
  ('11111111-1111-4111-8111-111111111102', 'lever', 'Lever Board', 'ats', 'https://example.com/lever'),
  ('11111111-1111-4111-8111-111111111103', 'linkedin', 'LinkedIn Alerts', 'job_board', 'https://example.com/linkedin'),
  ('11111111-1111-4111-8111-111111111104', 'djinni', 'Djinni', 'job_board', 'https://example.com/djinni')
on conflict (slug) do nothing;

insert into public.organizations (id, name, normalized_name, industry, location_text)
values
  ('22222222-2222-4222-8222-222222222201', 'Acme Analytics', 'acme analytics', 'SaaS', 'Remote'),
  ('22222222-2222-4222-8222-222222222202', 'Northwind Labs', 'northwind labs', 'Fintech', 'Berlin'),
  ('22222222-2222-4222-8222-222222222203', 'Orbit Systems', 'orbit systems', 'Infrastructure', 'London'),
  ('22222222-2222-4222-8222-222222222204', 'Pioneer Data', 'pioneer data', 'AI', 'Remote')
on conflict (normalized_name) do nothing;

insert into public.opportunities (
  id, provider_id, organization_id, title, normalized_title,
  opportunity_type, work_model, seniority, compensation_min, compensation_max,
  compensation_currency, created_at
)
values
  ('33333333-3333-4333-8333-333333333301', '11111111-1111-4111-8111-111111111101', '22222222-2222-4222-8222-222222222201', 'Senior Data Engineer', 'senior data engineer', 'employment', 'remote', 'senior', 90000, 120000, 'USD', now() - interval '42 days'),
  ('33333333-3333-4333-8333-333333333302', '11111111-1111-4111-8111-111111111102', '22222222-2222-4222-8222-222222222202', 'Analytics Engineer', 'analytics engineer', 'employment', 'hybrid', 'mid', 70000, 95000, 'EUR', now() - interval '35 days'),
  ('33333333-3333-4333-8333-333333333303', '11111111-1111-4111-8111-111111111103', '22222222-2222-4222-8222-222222222203', 'Platform Engineer', 'platform engineer', 'employment', 'remote', 'senior', 110000, 140000, 'USD', now() - interval '28 days'),
  ('33333333-3333-4333-8333-333333333304', '11111111-1111-4111-8111-111111111104', '22222222-2222-4222-8222-222222222204', 'ML Engineer', 'ml engineer', 'employment', 'remote', 'senior', 100000, 130000, 'USD', now() - interval '21 days'),
  ('33333333-3333-4333-8333-333333333305', '11111111-1111-4111-8111-111111111101', '22222222-2222-4222-8222-222222222201', 'Data Platform Lead', 'data platform lead', 'employment', 'remote', 'lead', 120000, 150000, 'USD', now() - interval '14 days'),
  ('33333333-3333-4333-8333-333333333306', '11111111-1111-4111-8111-111111111102', '22222222-2222-4222-8222-222222222202', 'Backend Engineer', 'backend engineer', 'employment', 'onsite', 'mid', 65000, 85000, 'EUR', now() - interval '7 days')
on conflict (id) do nothing;

insert into public.evaluations (id, opportunity_id, provider_id, score, recommendation, evaluated_at)
values
  ('44444444-4444-4444-8444-444444444401', '33333333-3333-4333-8333-333333333301', '11111111-1111-4111-8111-111111111101', 8.5, 'apply', now() - interval '40 days'),
  ('44444444-4444-4444-8444-444444444402', '33333333-3333-4333-8333-333333333302', '11111111-1111-4111-8111-111111111102', 7.2, 'apply', now() - interval '33 days'),
  ('44444444-4444-4444-8444-444444444403', '33333333-3333-4333-8333-333333333303', '11111111-1111-4111-8111-111111111103', 6.8, 'review', now() - interval '26 days'),
  ('44444444-4444-4444-8444-444444444404', '33333333-3333-4333-8333-333333333304', '11111111-1111-4111-8111-111111111104', 9.1, 'apply', now() - interval '19 days'),
  ('44444444-4444-4444-8444-444444444405', '33333333-3333-4333-8333-333333333305', '11111111-1111-4111-8111-111111111101', 7.9, 'apply', now() - interval '12 days'),
  ('44444444-4444-4444-8444-444444444406', '33333333-3333-4333-8333-333333333306', '11111111-1111-4111-8111-111111111102', 5.5, 'skip', now() - interval '5 days')
on conflict (id) do nothing;

insert into public.applications (
  id, opportunity_id, organization_id, provider_id, status, current_stage,
  applied_at, outcome, created_at, updated_at
)
values
  ('55555555-5555-4555-8555-555555555501', '33333333-3333-4333-8333-333333333301', '22222222-2222-4222-8222-222222222201', '11111111-1111-4111-8111-111111111101', 'active', 'tech_interview', current_date - 30, null, now() - interval '30 days', now() - interval '3 days'),
  ('55555555-5555-4555-8555-555555555502', '33333333-3333-4333-8333-333333333302', '22222222-2222-4222-8222-222222222202', '11111111-1111-4111-8111-111111111102', 'active', 'screening', current_date - 22, null, now() - interval '22 days', now() - interval '2 days'),
  ('55555555-5555-4555-8555-555555555503', '33333333-3333-4333-8333-333333333303', '22222222-2222-4222-8222-222222222203', '11111111-1111-4111-8111-111111111103', 'active', 'onsite', current_date - 18, null, now() - interval '18 days', now() - interval '1 day'),
  ('55555555-5555-4555-8555-555555555504', '33333333-3333-4333-8333-333333333304', '22222222-2222-4222-8222-222222222204', '11111111-1111-4111-8111-111111111104', 'active', 'offer', current_date - 12, 'offer_received', now() - interval '12 days', now() - interval '1 day'),
  ('55555555-5555-4555-8555-555555555505', '33333333-3333-4333-8333-333333333305', '22222222-2222-4222-8222-222222222201', '11111111-1111-4111-8111-111111111101', 'active', 'applied', current_date - 5, null, now() - interval '5 days', now() - interval '5 days'),
  ('55555555-5555-4555-8555-555555555506', '33333333-3333-4333-8333-333333333306', '22222222-2222-4222-8222-222222222202', '11111111-1111-4111-8111-111111111102', 'declined', 'declined', current_date - 8, 'declined', now() - interval '8 days', now() - interval '4 days')
on conflict (id) do nothing;

insert into public.application_events (id, application_id, event_type, event_at, title)
values
  ('66666666-6666-4666-8666-666666666601', '55555555-5555-4555-8555-555555555501', 'reply', now() - interval '25 days', 'Recruiter reply'),
  ('66666666-6666-4666-8666-666666666602', '55555555-5555-4555-8555-555555555502', 'interview_invite', now() - interval '15 days', 'Screening invite'),
  ('66666666-6666-4666-8666-666666666603', '55555555-5555-4555-8555-555555555503', 'response', now() - interval '12 days', 'Panel scheduled'),
  ('66666666-6666-4666-8666-666666666604', '55555555-5555-4555-8555-555555555504', 'reply', now() - interval '8 days', 'Offer discussion'),
  ('66666666-6666-4666-8666-666666666605', '55555555-5555-4555-8555-555555555501', 'interview_invite', now() + interval '3 days', 'Technical interview')
on conflict (id) do nothing;

insert into public.interviews (id, application_id, organization_id, stage, scheduled_at, result)
values
  ('77777777-7777-4777-8777-777777777701', '55555555-5555-4555-8555-555555555501', '22222222-2222-4222-8222-222222222201', 'technical', now() + interval '3 days', null),
  ('77777777-7777-4777-8777-777777777702', '55555555-5555-4555-8555-555555555502', '22222222-2222-4222-8222-222222222202', 'screening', now() - interval '10 days', 'passed'),
  ('77777777-7777-4777-8777-777777777703', '55555555-5555-4555-8555-555555555503', '22222222-2222-4222-8222-222222222203', 'onsite', now() - interval '5 days', 'passed'),
  ('77777777-7777-4777-8777-777777777704', '55555555-5555-4555-8555-555555555504', '22222222-2222-4222-8222-222222222204', 'final', now() - interval '2 days', 'offer')
on conflict (id) do nothing;

insert into public.automation_runs (
  id, provider_id, run_key, status, source_items_count, opportunities_count,
  evaluations_count, started_at, finished_at, created_at
)
values
  ('88888888-8888-4888-8888-888888888801', '11111111-1111-4111-8111-111111111101', 'demo-run-1', 'completed', 24, 6, 6, now() - interval '2 days', now() - interval '2 days' + interval '3 minutes', now() - interval '2 days'),
  ('88888888-8888-4888-8888-888888888802', '11111111-1111-4111-8111-111111111103', 'demo-run-2', 'completed', 18, 4, 4, now() - interval '1 day', now() - interval '1 day' + interval '2 minutes', now() - interval '1 day'),
  ('88888888-8888-4888-8888-888888888803', '11111111-1111-4111-8111-111111111104', 'demo-run-3', 'failed', 12, 0, 0, now() - interval '6 hours', now() - interval '6 hours' + interval '1 minute', now() - interval '6 hours')
on conflict (id) do nothing;

insert into public.automation_run_events (id, automation_run_id, run_key, event_type, severity, message, created_at)
values
  ('99999999-9999-4999-8999-999999999901', '88888888-8888-4888-8888-888888888801', 'demo-run-1', 'fetch_complete', 'info', 'Fetched 24 source items', now() - interval '2 days'),
  ('99999999-9999-4999-8999-999999999902', '88888888-8888-4888-8888-888888888802', 'demo-run-2', 'fetch_complete', 'info', 'Fetched 18 source items', now() - interval '1 day'),
  ('99999999-9999-4999-8999-999999999903', '88888888-8888-4888-8888-888888888803', 'demo-run-3', 'fetch_error', 'error', 'Upstream timeout', now() - interval '6 hours')
on conflict (id) do nothing;

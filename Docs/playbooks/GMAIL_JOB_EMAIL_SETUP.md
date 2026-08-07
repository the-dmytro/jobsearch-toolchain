# Gmail job email setup guide

Use this guide to route job-search email out of the main Inbox while keeping it available to Codex agents through the Gmail connector.

## Goal

- Job alerts and application/recruiter responses should skip the Inbox.
- They should remain visible under Gmail labels.
- Codex automations should process each stream by label/search query.
- Emails should remain unread unless you or an automation intentionally changes that later.

In Gmail, labels are the folder equivalent. "Skip the Inbox" archives the email, but it still stays in All Mail and under its labels.

## Labels to create

Open Gmail:

1. Settings gear.
2. See all settings.
3. Labels.
4. Create these labels. Use nested labels if Gmail offers "Nest label under".

Recommended labels:

```text
Job/Alerts/LinkedIn
Job/Alerts/Upwork
Job/Alerts/Other

Job/Responses/Company
Job/Responses/Recruiters
Job/Responses/Interview
Job/Responses/Rejection
Job/Responses/Offer
Job/Responses/Upwork

Job/Automation/Processed
Job/Automation/NeedsReview
```

Keep these labels visible in the label list, at least while validating the setup.

## Filter settings

For each filter:

1. Use Gmail search bar options or Settings -> Filters and Blocked Addresses -> Create a new filter.
2. Paste the whole query into "Has the words" unless a specific field is listed.
3. Treat each `Query:` block in this guide as one Gmail search expression. If the query wraps onto multiple lines in this document, that is only formatting. Paste it as one continuous value.
4. Click "Create filter".
5. Select:
   - Skip the Inbox
   - Apply the matching label
   - Never send it to Spam
   - Also apply filter to matching conversations, only if you want immediate backfill
6. Do not select:
   - Mark as read
   - Delete it

## Filters to create

### LinkedIn job alerts

Query:

```text
from:(jobalerts-noreply@linkedin.com OR jobs-listings@linkedin.com OR jobs-noreply@linkedin.com)
```

Action:

```text
Apply label: Job/Alerts/LinkedIn
Skip Inbox: yes
```

### LinkedIn recruiter or job-related LinkedIn messages

Query:

```text
from:(messages-noreply@linkedin.com OR messaging-digest-noreply@linkedin.com OR invitations@linkedin.com) (recruiter OR hiring OR opportunity OR interview OR application)
```

Action:

```text
Apply label: Job/Responses/Recruiters
Skip Inbox: yes, if you are comfortable hiding these from Inbox
```

If you want a safer first week, apply the label but do not skip the Inbox for this filter yet.

### Upwork job alerts

Query:

```text
from:(alerts@upwork.com OR noreply@upwork.com OR donotreply@upwork.com OR notifications@upwork.com) (subject:"New job" OR subject:"Recommended jobs" OR "saved search" OR "jobs you might like")
```

Action:

```text
Apply label: Job/Alerts/Upwork
Skip Inbox: yes
```

### Upwork messages, invites, contracts, and responses

Query:

```text
from:(messages-noreply@upwork.com OR notifications@upwork.com OR noreply@upwork.com OR donotreply@upwork.com) (interview OR invitation OR invite OR message OR offer OR contract OR proposal)
```

Action:

```text
Apply label: Job/Responses/Upwork
Skip Inbox: yes
```

### ATS and company application responses

Query:

```text
from:(greenhouse.io OR greenhouse-mail.io OR lever.co OR ashbyhq.com OR workablemail.com OR smartrecruiters.com OR teamtailor.com OR recruitee.com OR breezy-mail.com OR jobs.lever.co OR myworkday.com)
```

Action:

```text
Apply label: Job/Responses/Company
Skip Inbox: yes
```

### Interview scheduling

Query:

```text
(interview OR "schedule a call" OR "schedule time" OR calendly OR "Google Meet" OR Zoom OR "Microsoft Teams") (application OR role OR position OR recruiter OR hiring)
```

Action:

```text
Apply label: Job/Responses/Interview
Skip Inbox: no for the first week; yes after confirming it is not too broad
```

This filter is intentionally keyword-based and can overmatch. Use it mostly as an extra label.

### Rejections

Query:

```text
("not moving forward" OR "decided not to proceed" OR "not selected" OR unsuccessful OR unfortunately OR declined)
```

Action:

```text
Apply label: Job/Responses/Rejection
Skip Inbox: no
```

Use this as an extra label only. The company/ATS filter should already move most of these out of the Inbox.

### Offers and late-stage emails

Query:

```text
(from:(greenhouse.io OR greenhouse-mail.io OR lever.co OR ashbyhq.com OR workablemail.com OR smartrecruiters.com OR teamtailor.com OR recruitee.com OR breezy-mail.com OR jobs.lever.co OR myworkday.com OR linkedin.com OR upwork.com) OR (recruiter OR hiring OR talent OR sourcer)) ("offer letter" OR "written offer" OR "verbal offer" OR "employment agreement" OR contract OR "compensation package" OR salary OR equity OR "signing bonus" OR "background check" OR "reference check") -from:{{REPORT_EMAIL}} -subject:"LinkedIn job triage" -subject:"Upwork job alerts"
```

Action:

```text
Apply label: Job/Responses/Offer
Skip Inbox: no
```

Use this as an extra label only. It is intentionally broad.
It is narrower than the first version on purpose. `next step`, `next steps`, and bare `compensation` were removed because they overmatch summary emails and unrelated mail.

## Validation

After creating filters:

1. Send no test emails. Instead, use Gmail search.
2. Search each label or click it in the sidebar:

```text
label:"Job/Alerts/LinkedIn"
label:"Job/Alerts/Upwork"
label:"Job/Responses/Company"
label:"Job/Responses/Upwork"
```

3. Confirm matching emails appear.
4. Confirm those emails are not in Inbox if the filter has "Skip Inbox".
5. Confirm they remain unread if they were unread before.

If Gmail does not accept quoted label search with nested labels, click the label in the left sidebar and copy the search expression Gmail generates. We can use that exact expression in Codex automations.

## What to tell Codex after setup

Return to Codex and report:

- Which labels you created.
- Which filters have "Skip Inbox" enabled.
- Whether you applied filters to existing conversations.
- Any labels whose Gmail search syntax looked different from the examples.

Then Codex can:

- backfill labels on older matching emails if needed
- update LinkedIn and Upwork automations to search label-specific streams
- add a new automation for company/recruiter responses
- update Supabase when responses, interviews, rejections, or offers arrive
- send a concise summary email to `{{REPORT_EMAIL}}`

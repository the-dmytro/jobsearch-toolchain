# Writing a notifier connector

Notifiers receive a `RunReport` only after a deterministic run succeeds far enough to report. Built-ins include email, webhook, Slack, and Telegram; all are opt-in.

Built-ins accept environment-variable references so tokens and private recipients stay
out of TOML:

```toml
[notify.email]
kind = "email"
to_env = "JOBTRACKER_REPORT_EMAIL_TO"

[notify.webhook]
kind = "webhook"
url_env = "JOBTRACKER_WEBHOOK_URL"

[notify.slack]
kind = "slack"
webhook_url_env = "JOBTRACKER_SLACK_WEBHOOK_URL"

[notify.telegram]
kind = "telegram"
bot_token_env = "JOBTRACKER_TELEGRAM_BOT_TOKEN"
chat_id_env = "JOBTRACKER_TELEGRAM_CHAT_ID"
```

Literal `to`, `url`, `webhook_url`, `bot_token`, and `chat_id` values remain
compatible for ignored local config, but public examples and shared config should use
environment references.

Plugins use `jobtracker.notifiers` and a factory accepting `ConnectorBuildContext`:

```toml
[project.entry-points."jobtracker.notifiers"]
private_channel = "private_notify.plugin:build_notifier"
```

```python
class PrivateNotifier:
    slug = "private_channel"

    def notify(self, report):
        return {"sent": True}

    def health(self):
        return []

def build_notifier(context):
    return PrivateNotifier()
```

Read secrets from documented environment variables. Test success, failure, idempotency where relevant, redaction, and `health()` without sending a message.

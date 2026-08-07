import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure deployment env vars — nothing stored in-browser.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Auth allowlist</CardTitle>
          <CardDescription>
            Set <code className="rounded bg-muted px-1">CRM_OWNER_EMAIL</code> on the server (comma-separated).
            DB policy uses <code className="rounded bg-muted px-1">crm_owner_allowlist</code> — keep emails in sync.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>
            Supabase Dashboard → Authentication → URL configuration: add site URL and redirect{" "}
            <code className="rounded bg-muted px-1">/auth/callback</code>.
          </p>
          <p>
            For signed artifact URLs, set <code className="rounded bg-muted px-1">SUPABASE_SERVICE_ROLE_KEY</code>{" "}
            (or <code className="rounded bg-muted px-1">SUPABASE_SECRET_KEY</code>) where the CRM server runs.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

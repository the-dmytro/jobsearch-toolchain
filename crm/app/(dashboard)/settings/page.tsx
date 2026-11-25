import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageHeader } from "@/components/crm/page-header";
import { ThemeSelect } from "@/components/crm/theme-select";
import packageJson from "@/package.json";
import { createClient } from "@/lib/supabase/server";

type EnvironmentLabel = "Production" | "Preview" | "Development";

/**
 * Maps the hosting environment to a readable label. Vercel's VERCEL_ENV wins
 * when present. Otherwise NODE_ENV decides, so a local `next start` reads as
 * Production.
 */
function environmentLabel(): EnvironmentLabel {
  switch (process.env.VERCEL_ENV) {
    case "production":
      return "Production";
    case "preview":
      return "Preview";
    case "development":
      return "Development";
    default:
      return process.env.NODE_ENV === "production" ? "Production" : "Development";
  }
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[10rem_1fr] sm:gap-4">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-sm text-foreground">{children}</dd>
    </div>
  );
}

/**
 * Account, deployment and appearance settings. Only information that is safe to
 * show a signed-in owner is included: no keys, secrets or internal configuration.
 */
export default async function SettingsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const email = user?.email ?? "Not available";
  const environment = environmentLabel();
  const version = packageJson.version;
  const commit = process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6">
      <PageHeader
        title="Settings"
        description="Your account, this deployment, and how the app looks on this device."
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Account</CardTitle>
          <CardDescription>The address you use to sign in.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl>
            <DetailRow label="Signed in as">{email}</DetailRow>
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">About this deployment</CardTitle>
          <CardDescription>Where this copy of the app is running.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl>
            <DetailRow label="Environment">{environment}</DetailRow>
            <DetailRow label="Version">
              <span className="tabular-nums">{version}</span>
            </DetailRow>
            {commit ? (
              <DetailRow label="Build">
                <span className="font-mono text-xs tabular-nums">{commit}</span>
              </DetailRow>
            ) : null}
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Appearance</CardTitle>
          <CardDescription>
            Follow your system setting, or pick light or dark. Saved on this device only.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ThemeSelect />
        </CardContent>
      </Card>
    </div>
  );
}

"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { sendMagicLink } from "./actions";

export function LoginForm({ error }: { error: string | null }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setLoading(true);

    try {
      const result = await sendMagicLink(email);
      if (result.ok) {
        setSent(true);
      } else {
        setFormError(result.message);
      }
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Could not send magic link."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>JobSearch CRM</CardTitle>
          <CardDescription>
            Magic link sign-in. Same email must be in CRM owner allowlist.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error === "forbidden" && (
            <p className="mb-4 text-sm text-destructive">
              Email not allowed. Update CRM_OWNER_EMAIL or crm_owner_allowlist.
            </p>
          )}
          {error === "auth" && (
            <p className="mb-4 text-sm text-destructive">
              Auth failed. Try again or check Supabase redirect URLs.
            </p>
          )}
          {formError && (
            <p className="mb-4 text-sm text-destructive">{formError}</p>
          )}
          {sent ? (
            <p className="text-sm text-muted-foreground">
              Check your inbox for the login link sent to{" "}
              <span className="font-medium text-foreground">{email.trim()}</span>
              .
            </p>
          ) : (
            <form onSubmit={onSubmit} className="flex flex-col gap-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                />
              </div>
              <Button type="submit" disabled={loading}>
                {loading ? "Sending…" : "Send magic link"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

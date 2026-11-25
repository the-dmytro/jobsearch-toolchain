"use client";

import { useId, useState } from "react";
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

const FORBIDDEN_MESSAGE =
  "This account doesn't have access. Sign in with the owner email.";
const AUTH_MESSAGE =
  "The sign-in link didn't work. It may have expired. Request a new one below.";

/**
 * Email sign-in form. It sends a one-time link and never asks for a password.
 * `error` comes from the query string when the callback or the owner check
 * rejects a sign-in.
 */
export function LoginForm({ error }: { error: string | null }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const emailId = useId();
  const hintId = `${emailId}-hint`;

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
        err instanceof Error && err.message
          ? err.message
          : "We couldn't send the sign-in link. Try again in a moment."
      );
    } finally {
      setLoading(false);
    }
  }

  const pageError =
    error === "forbidden" ? FORBIDDEN_MESSAGE : error === "auth" ? AUTH_MESSAGE : null;
  const visibleError = formError ?? pageError;

  return (
    <div className="flex min-h-screen items-center justify-center p-4 sm:p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign in to JobSearch CRM</CardTitle>
          <CardDescription>
            We&apos;ll email you a sign-in link. No password needed.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {visibleError ? (
            <p role="alert" className="text-sm text-danger">
              {visibleError}
            </p>
          ) : null}

          {sent ? (
            <div role="status" className="space-y-4">
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">Check your inbox</p>
                <p className="text-sm text-muted-foreground">
                  We sent a sign-in link to{" "}
                  <span className="font-medium text-foreground">{email.trim()}</span>. Open it on
                  this device to finish signing in.
                </p>
              </div>
              <p className="text-xs text-muted-foreground">
                Nothing yet? Check your spam folder, or wait a minute and try again.
              </p>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => {
                  setSent(false);
                  setFormError(null);
                }}
              >
                Use a different email
              </Button>
            </div>
          ) : (
            <form
              onSubmit={onSubmit}
              className="flex flex-col gap-4"
              aria-busy={loading}
            >
              <div className="space-y-2">
                <Label htmlFor={emailId}>Email address</Label>
                <Input
                  id={emailId}
                  name="email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                  aria-describedby={hintId}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                />
                <p id={hintId} className="text-xs text-muted-foreground">
                  Use the address you signed up with.
                </p>
              </div>
              <Button type="submit" disabled={loading} className="w-full">
                {loading ? "Sending link…" : "Email me a sign-in link"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

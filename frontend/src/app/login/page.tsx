"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth-store";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { login, error } = useAuthStore();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    await login(email, password);
    if (useAuthStore.getState().user) {
      router.push("/");
    }
    setSubmitting(false);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm glass border-border">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl flex items-center justify-center gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 512 512"
              className="size-8"
              aria-hidden="true"
            >
              <rect width="512" height="512" rx="108" fill="#0B1120" />
              <rect x="100" y="312" width="72" height="120" rx="10" fill="#06B6D4" opacity="0.55" />
              <rect x="220" y="216" width="72" height="216" rx="10" fill="#06B6D4" opacity="0.75" />
              <rect x="340" y="120" width="72" height="312" rx="10" fill="#06B6D4" />
              <polyline points="136,312 256,216 376,120" fill="none" stroke="#06B6D4" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="376" cy="120" r="18" fill="#fff" opacity="0.9" />
              <circle cx="376" cy="120" r="10" fill="#06B6D4" />
            </svg>
            <span>Insight<span className="text-primary dark:text-cyan-accent">Xpert</span></span>
          </CardTitle>
          <CardDescription>Sign in to your account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <Input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
            <div className="flex flex-col gap-2">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
              />
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Signing in..." : "Sign in"}
            </Button>
            {error && (
              <p className="text-sm text-center text-destructive">{error}</p>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

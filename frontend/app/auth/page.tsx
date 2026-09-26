"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { Logo } from "@/components/shared/logo";
import { AuthErrorBoundary } from "@/components/shared/error-boundary";
import { PageTransition } from "@/components/shared/page-transition";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/contexts/auth-context";

const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
});

type FormValues = z.infer<typeof schema>;

export default function AuthPage(): React.JSX.Element {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [authError, setAuthError] = useState<string | null>(null);
  const { signIn, signUp } = useAuth();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async ({ email, password }) => {
    setAuthError(null);
    try {
      if (mode === "signin") await signIn(email, password);
      else await signUp(email, password);
      router.push("/upload");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Authentication failed.");
    }
  });

  return (
    <PageTransition>
      <main id="main" className="min-h-screen bg-surface grid lg:grid-cols-2">
        <section className="hidden lg:flex flex-col justify-between bg-primary-fixed/40 p-12">
          <Logo />
          <div>
            <h1 className="font-headline-lg text-headline-lg text-on-surface max-w-md">
              Legal clarity, without the hourly billing.
            </h1>
            <p className="mt-3 font-body-lg text-on-surface-variant max-w-md">
              Join 40,000+ freelancers, founders, and renters who read every contract with Lexi first.
            </p>
          </div>
          <p className="lexi-code">SOC-2 Type II • Zero-retention • 256-bit encryption</p>
        </section>
        <section className="flex items-center justify-center p-6 md:p-12">
          <div className="w-full max-w-md">
            <AuthErrorBoundary>
            <div className="lg:hidden mb-8"><Logo /></div>
            <h2 className="font-headline-lg text-headline-lg text-on-surface">
              {mode === "signin" ? "Welcome back" : "Create your account"}
            </h2>
            <p className="mt-1 font-body-md text-on-surface-variant">
              {mode === "signin" ? "Sign in to continue to your workspace." : "Start analyzing documents in minutes."}
            </p>
            <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
              <div>
                <label htmlFor="email" className="lexi-label">Email</label>
                <Input id="email" type="email" autoComplete="email" placeholder="ada@example.com" {...register("email")} aria-invalid={!!errors.email} />
                {errors.email ? <p role="alert" className="mt-1 font-label-sm text-error">{errors.email.message}</p> : null}
              </div>
              <div>
                <label htmlFor="password" className="lexi-label">Password</label>
                <Input id="password" type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} placeholder="••••••••" {...register("password")} aria-invalid={!!errors.password} />
                {errors.password ? <p role="alert" className="mt-1 font-label-sm text-error">{errors.password.message}</p> : null}
              </div>
              <Button type="submit" disabled={isSubmitting} className="w-full">
                {isSubmitting ? "Please wait…" : mode === "signin" ? "Sign In" : "Create Account"}
              </Button>
            </form>
            {authError ? <p role="alert" className="mt-3 font-label-sm text-error">{authError}</p> : null}
            <p className="mt-6 font-body-md text-on-surface-variant">
              {mode === "signin" ? "New to Lexi? " : "Already have an account? "}
              <button
                type="button"
                className="font-semibold text-primary hover:underline min-h-[44px]"
                onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
              >
                {mode === "signin" ? "Create an account" : "Sign in"}
              </button>
            </p>
            <Link href="/dashboard" className="mt-2 inline-flex min-h-[44px] items-center font-label-md text-on-surface-variant hover:text-on-surface">
              ← Continue as guest to the demo
            </Link>
            </AuthErrorBoundary>
          </div>
        </section>
      </main>
    </PageTransition>
  );
}

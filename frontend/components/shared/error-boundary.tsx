"use client";

import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

type ErrorBoundaryProps = {
  children: ReactNode;
  /** Label shown in the fallback card, e.g. "Dashboard". */
  area: string;
  /** Where to send the user on reset, e.g. "/dashboard". */
  resetHref?: string;
};

type ErrorBoundaryState = { error: Error | null };

/**
 * Generic render-crash boundary: catches render errors in its subtree and
 * renders a retry card instead of a white screen. Never touches the dev
 * server — render-only, no process APIs, no side effects beyond logging.
 */
class LexiErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(): void {
    // Log-only in development; never terminates the process.
  }

  private retry = (): void => this.setState({ error: null });

  render(): ReactNode {
    const { error } = this.state;
    if (error === null) return this.props.children;
    return (
      <div className="lexi-card p-6 text-center" role="alert" aria-label={`${this.props.area} error`}>
        <h2 className="font-headline-sm text-headline-sm text-on-surface">
          Something went wrong in {this.props.area}.
        </h2>
        <p className="mx-auto mt-2 max-w-md font-body-md text-on-surface-variant">
          Your documents are safe — this view just failed to render. Try again, or go back to safety.
        </p>
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          <Button onClick={this.retry}>Retry</Button>
          <a href={this.props.resetHref ?? "/dashboard"} className="lexi-btn-secondary">
            Back to dashboard
          </a>
        </div>
      </div>
    );
  }
}

export function AuthErrorBoundary({ children }: { children: ReactNode }): React.JSX.Element {
  return (
    <LexiErrorBoundary area="Authentication" resetHref="/auth">
      {children}
    </LexiErrorBoundary>
  );
}

export function DashboardErrorBoundary({ children }: { children: ReactNode }): React.JSX.Element {
  return (
    <LexiErrorBoundary area="Dashboard" resetHref="/dashboard">
      {children}
    </LexiErrorBoundary>
  );
}

export function ProcessingErrorBoundary({ children }: { children: ReactNode }): React.JSX.Element {
  return (
    <LexiErrorBoundary area="Processing" resetHref="/upload">
      {children}
    </LexiErrorBoundary>
  );
}

export function ChatErrorBoundary({ children }: { children: ReactNode }): React.JSX.Element {
  return (
    <LexiErrorBoundary area="AI Chat" resetHref="/dashboard">
      {children}
    </LexiErrorBoundary>
  );
}

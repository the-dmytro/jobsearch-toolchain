"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorState } from "@/components/crm/error-state";

type ErrorBoundaryProps = {
  children: ReactNode;
  /** Headline shown in the fallback, for example "Insights failed to render". */
  title?: string;
  /** Fixed message for the fallback. Defaults to a message derived from the error. */
  description?: string;
};

type ErrorBoundaryState = {
  error: unknown;
  hasError: boolean;
};

/**
 * Section-level error boundary for client-rendered content. Its fallback is the
 * shared `ErrorState`, so the raw error message is never printed. "Try again"
 * clears the boundary and re-renders the children.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null, hasError: false };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return { error, hasError: true };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error("CRM error boundary:", error, info.componentStack);
  }

  private handleRetry = () => {
    this.setState({ error: null, hasError: false });
  };

  render() {
    if (this.state.hasError) {
      return (
        <ErrorState
          title={this.props.title ?? "Something went wrong"}
          description={this.props.description}
          error={this.state.error}
          onRetry={this.handleRetry}
        />
      );
    }

    return this.props.children;
  }
}

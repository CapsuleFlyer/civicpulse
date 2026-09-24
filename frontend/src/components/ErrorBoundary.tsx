import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/**
 * A render error in one view must not leave an operator staring at a white
 * page in the middle of a shift, so the boundary explains what broke and offers
 * the one action that helps.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Console is the browser's stdout; a real deployment ships this to Sentry.
    console.error("CivicPulse render error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page stack">
        <h1>This screen stopped working</h1>
        <p>
          The page hit an error while rendering and cannot continue. Your data was not affected —
          reload to start again.
        </p>
        <p className="mono">{this.state.error.message}</p>
        <button className="button" onClick={() => window.location.reload()}>
          Reload the page
        </button>
      </div>
    );
  }
}

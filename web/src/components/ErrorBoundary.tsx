import { Component, type ErrorInfo, type ReactNode } from "react";
import "./error-boundary.css";

type Props = {
  /** What this boundary guards, as the operator would say it: "Operator console", "Preview for". */
  name: string;
  children: ReactNode;
};

type State = { error: Error | null };

/**
 * Contains a render error to the part of the page that threw.
 *
 * Without one, React unmounts the whole tree, and /multiview embeds the Operator beside three viewers,
 * so one bad field blanked all four. This shows what failed and leaves everything outside it running.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`${this.props.name} failed to render:`, error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="boundary" role="alert">
        <b>{this.props.name} stopped working.</b>
        <p>
          It hit an error while drawing: <code>{error.message || error.name}</code>. The rest of the page is still
          running. The browser console has the details.
        </p>
        <button type="button" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}

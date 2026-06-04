import { Component, ErrorInfo, ReactNode } from 'react';
import { J } from '../screens/jarvis-shared';

interface Props {
  children: ReactNode;
  label?: string;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[ErrorBoundary:${this.props.label ?? 'app'}]`, error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, padding: 32, gap: 12, color: J.textMuted }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: J.error }}>Something went wrong</div>
        <pre style={{ fontSize: 11, color: J.textMuted, background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, padding: '10px 14px', maxWidth: 480, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {this.state.error.message}
        </pre>
        <button
          onClick={() => this.setState({ error: null })}
          style={{ fontSize: 12, padding: '6px 16px', borderRadius: 6, background: J.bg3, border: `1px solid ${J.border}`, color: J.textSec, cursor: 'pointer' }}>
          Try again
        </button>
      </div>
    );
  }
}

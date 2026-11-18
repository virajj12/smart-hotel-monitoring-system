import React, { Component, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('Surveillance Dashboard crashed:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          backgroundColor: '#0f0f12',
          color: '#f4f4f5',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
        }}>
          <div style={{
            maxWidth: '560px',
            width: '100%',
            backgroundColor: '#18181c',
            border: '1px solid #27272a',
            borderRadius: '12px',
            padding: '28px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
              <span style={{ fontSize: '24px' }}>⚠️</span>
              <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#f87171' }}>
                Surveillance UI Runtime Error
              </h2>
            </div>
            <p style={{ fontSize: '14px', color: '#a1a1aa', margin: '0 0 16px 0', lineHeight: 1.5 }}>
              The monitoring interface encountered an unhandled rendering error:
            </p>
            <pre style={{
              backgroundColor: '#09090b',
              border: '1px solid #27272a',
              borderRadius: '8px',
              padding: '12px',
              fontSize: '12px',
              color: '#fb7185',
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              marginBottom: '20px',
              fontFamily: 'JetBrains Mono, monospace',
            }}>
              {this.state.error?.message || String(this.state.error)}
            </pre>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button
                onClick={() => window.location.reload()}
                style={{
                  backgroundColor: '#27272a',
                  color: '#ffffff',
                  border: '1px solid #3f3f46',
                  borderRadius: '6px',
                  padding: '8px 16px',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Reload Dashboard
              </button>
              <button
                onClick={() => { localStorage.clear(); window.location.reload(); }}
                style={{
                  backgroundColor: 'transparent',
                  color: '#a1a1aa',
                  border: '1px solid #27272a',
                  borderRadius: '6px',
                  padding: '8px 16px',
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                Clear Cache &amp; Reload
              </button>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)

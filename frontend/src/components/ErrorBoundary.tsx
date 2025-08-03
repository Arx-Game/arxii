import { ReactNode } from 'react'
import { ErrorBoundary as ReactErrorBoundary } from 'react-error-boundary'

interface Props {
  children: ReactNode
}

function ErrorFallback({ resetErrorBoundary }: { resetErrorBoundary: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-red-600">Something went wrong</h2>
        <p className="mt-2 text-muted-foreground">Please refresh the page and try again.</p>
        <button
          onClick={resetErrorBoundary}
          className="mt-4 rounded bg-blue-500 px-4 py-2 text-white hover:bg-blue-600"
        >
          Try again
        </button>
      </div>
    </div>
  )
}

export function ErrorBoundary({ children }: Props) {
  return (
    <ReactErrorBoundary
      FallbackComponent={ErrorFallback}
      onError={(error, errorInfo) => {
        console.error('Uncaught error:', error, errorInfo)
      }}
    >
      {children}
    </ReactErrorBoundary>
  )
}

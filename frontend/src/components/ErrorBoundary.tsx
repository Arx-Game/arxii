import { ReactNode } from 'react';
import { ErrorBoundary as ReactErrorBoundary } from 'react-error-boundary';
import { QueryErrorResetBoundary } from '@tanstack/react-query';

interface Props {
  children: ReactNode;
}

function ErrorFallback({
  error,
  resetErrorBoundary,
}: {
  error: Error;
  resetErrorBoundary: () => void;
}) {
  const isDevelopment = import.meta.env.DEV;

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="mx-auto max-w-2xl p-6 text-center">
        <h2 className="text-2xl font-bold text-red-600">Something went wrong</h2>
        <p className="mt-2 text-muted-foreground">{error.message}</p>

        {isDevelopment && (
          <details className="mt-4 text-left">
            <summary className="cursor-pointer text-sm font-medium">
              🐛 Debug Info (Development Only)
            </summary>
            <pre className="mt-2 overflow-auto rounded bg-gray-100 p-4 text-xs dark:bg-gray-800">
              <strong>Error:</strong> {error.name}: {error.message}
              {error.stack && (
                <>
                  <br />
                  <strong>Stack:</strong>
                  <br />
                  {error.stack}
                </>
              )}
            </pre>
          </details>
        )}

        <button
          onClick={resetErrorBoundary}
          className="mt-4 rounded bg-blue-500 px-4 py-2 text-white hover:bg-blue-600"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

export function ErrorBoundary({ children }: Props) {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ReactErrorBoundary
          FallbackComponent={ErrorFallback}
          onReset={reset}
          onError={(error, errorInfo) => {
            console.error('🚨 Uncaught React Error:');
            console.error('Error:', error);
            console.error('Error Info:', errorInfo);
            console.error('Stack:', error.stack);

            // In development, also log to help debug
            if (import.meta.env.DEV) {
              console.group('🐛 Debug Information');
              console.log('Error Name:', error.name);
              console.log('Error Message:', error.message);
              console.log('Component Stack:', errorInfo.componentStack);
              console.groupEnd();
            }
          }}
        >
          {children}
        </ReactErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}

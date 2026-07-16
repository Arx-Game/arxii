import { ReactNode } from 'react';
import { ErrorBoundary as ReactErrorBoundary } from 'react-error-boundary';
import { QueryErrorResetBoundary } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Home, RefreshCw } from 'lucide-react';

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
  const navigate = useNavigate();

  const goHome = () => {
    resetErrorBoundary();
    navigate('/');
  };

  const reloadPage = () => {
    window.location.reload();
  };

  return (
    <div className="flex min-h-screen items-center justify-center">
      <Card className="mx-auto max-w-2xl">
        <CardHeader>
          <CardTitle className="text-2xl text-red-600">Something went wrong</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-center">
          <p className="text-muted-foreground">{error.message}</p>

          {isDevelopment && (
            <details className="text-left">
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

          <div className="flex justify-center gap-2">
            <Button onClick={resetErrorBoundary} variant="outline">
              Try again
            </Button>
            <Button onClick={goHome}>
              <Home className="mr-2 h-4 w-4" />
              Go Home
            </Button>
            <Button onClick={reloadPage} variant="outline">
              <RefreshCw className="mr-2 h-4 w-4" />
              Reload
            </Button>
          </div>
        </CardContent>
      </Card>
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

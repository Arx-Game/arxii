/**
 * Stage Error Boundary
 *
 * Error boundary specific to character creation stages.
 * Provides navigation options when a stage fails to render.
 */

import { ReactNode } from 'react';
import { ErrorBoundary as ReactErrorBoundary } from 'react-error-boundary';
import { QueryErrorResetBoundary } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { AlertCircle, ArrowLeft, RefreshCw, Home } from 'lucide-react';
import { Stage } from '../types';

interface Props {
  children: ReactNode;
  currentStage: Stage;
  onNavigateToStage: (stage: Stage) => void;
}

interface ErrorFallbackProps {
  error: Error;
  resetErrorBoundary: () => void;
  currentStage: Stage;
  onNavigateToStage: (stage: Stage) => void;
}

function StageErrorFallback({
  error,
  resetErrorBoundary,
  currentStage,
  onNavigateToStage,
}: ErrorFallbackProps) {
  const isDevelopment = import.meta.env.DEV;
  const canGoBack = currentStage > Stage.ORIGIN;

  const handlePreviousStage = () => {
    const previousStage = (currentStage - 1) as Stage;
    onNavigateToStage(previousStage);
    resetErrorBoundary();
  };

  const handleFirstStage = () => {
    onNavigateToStage(Stage.ORIGIN);
    resetErrorBoundary();
  };

  return (
    <div className="flex min-h-[400px] items-center justify-center">
      <div className="mx-auto max-w-2xl rounded-lg border border-destructive/50 bg-destructive/10 p-8">
        <div className="flex items-start gap-3">
          <AlertCircle className="mt-0.5 h-6 w-6 flex-shrink-0 text-destructive" />
          <div className="flex-1">
            <h2 className="text-xl font-bold text-destructive">Stage Error</h2>
            <p className="mt-2 text-sm text-muted-foreground">{error.message}</p>

            {isDevelopment && (
              <details className="mt-4">
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

            <div className="mt-6 flex flex-wrap gap-2">
              {canGoBack && (
                <Button onClick={handlePreviousStage} variant="default">
                  <ArrowLeft className="mr-2 h-4 w-4" />
                  Previous Step
                </Button>
              )}

              <Button onClick={resetErrorBoundary} variant="outline">
                <RefreshCw className="mr-2 h-4 w-4" />
                Try Again
              </Button>

              {currentStage !== Stage.ORIGIN && (
                <Button onClick={handleFirstStage} variant="ghost">
                  <Home className="mr-2 h-4 w-4" />
                  First Step
                </Button>
              )}
            </div>

            <p className="mt-4 text-xs text-muted-foreground">
              You can also use the stage navigation at the top to jump to any step.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export function StageErrorBoundary({ children, currentStage, onNavigateToStage }: Props) {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ReactErrorBoundary
          FallbackComponent={(props) => (
            <StageErrorFallback
              {...props}
              currentStage={currentStage}
              onNavigateToStage={onNavigateToStage}
            />
          )}
          onReset={reset}
          onError={(error, errorInfo) => {
            console.error('🚨 Character Creation Stage Error:');
            console.error('Stage:', Stage[currentStage]);
            console.error('Error:', error);
            console.error('Error Info:', errorInfo);
            console.error('Stack:', error.stack);

            if (import.meta.env.DEV) {
              console.group('🐛 Stage Debug Information');
              console.log('Current Stage:', currentStage);
              console.log('Error Name:', error.name);
              console.log('Error Message:', error.message);
              console.log('Component Stack:', errorInfo.componentStack);
              console.groupEnd();
            }
          }}
          resetKeys={[currentStage]}
        >
          {children}
        </ReactErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}

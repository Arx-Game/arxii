import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { store } from './store/store';
import { queryClient } from './queryClient';
import { AuthProvider } from './components/AuthProvider';
import { ThemeProvider } from './components/theme-provider';
import { RealmThemeProvider } from './components/realm-theme-provider';
import { ErrorBoundary } from './components/ErrorBoundary';
import App from './App';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <ErrorBoundary>
          <AuthProvider>
            <BrowserRouter
              future={{
                v7_startTransition: true,
                v7_relativeSplatPath: true,
              }}
            >
              <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
                <RealmThemeProvider>
                  <App />
                </RealmThemeProvider>
              </ThemeProvider>
            </BrowserRouter>
          </AuthProvider>
        </ErrorBoundary>
      </QueryClientProvider>
    </Provider>
  </StrictMode>
);

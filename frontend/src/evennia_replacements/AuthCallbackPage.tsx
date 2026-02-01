import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAppDispatch } from '@/store/hooks';
import { setAccount } from '@/store/authSlice';
import { fetchAccount } from './api';

export function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const dispatch = useAppDispatch();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function handleCallback() {
      // Check for error in URL params
      const errorParam = searchParams.get('error');
      if (errorParam) {
        setError(`Authentication failed: ${errorParam}`);
        return;
      }

      try {
        // The OAuth callback has already been processed by Django
        // The session cookie should be set. Fetch the user data.
        const account = await fetchAccount();

        if (account) {
          // Update Redux store with the account data
          dispatch(setAccount(account));

          // Invalidate queries to refresh data
          queryClient.invalidateQueries({ queryKey: ['account'] });

          // Check if email is verified
          if (!account.email_verified) {
            navigate('/account/unverified');
          } else {
            navigate('/');
          }
        } else {
          // No account returned - authentication may have failed
          setError('Authentication failed. Please try again.');
        }
      } catch (err) {
        console.error('Auth callback error:', err);
        setError('Failed to complete authentication. Please try again.');
      }
    }

    handleCallback();
  }, [searchParams, navigate, queryClient, dispatch]);

  if (error) {
    return (
      <div className="mx-auto max-w-sm text-center">
        <h1 className="mb-4 text-xl font-bold text-red-600">Login Failed</h1>
        <p className="mb-4">{error}</p>
        <a href="/login" className="text-blue-500 hover:underline">
          Try again
        </a>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-sm text-center">
      <p>Completing login...</p>
    </div>
  );
}

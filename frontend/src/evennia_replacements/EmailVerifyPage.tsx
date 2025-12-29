import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { verifyEmail } from './api';
import { SITE_NAME } from '@/config';
import { Button } from '@/components/ui/button';

export function EmailVerifyPage() {
  const { key } = useParams<{ key: string }>();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying');
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    const performVerification = async () => {
      if (!key) {
        setStatus('error');
        setErrorMessage('Invalid verification link - missing key');
        return;
      }

      try {
        await verifyEmail(key);
        setStatus('success');

        // Redirect to home page after a short delay (user is now verified)
        setTimeout(() => {
          navigate('/', {
            replace: true,
          });
        }, 2000);
      } catch (error) {
        setStatus('error');
        setErrorMessage(
          error instanceof Error
            ? error.message
            : 'Failed to verify email. The link may be expired or invalid.'
        );
      }
    };

    performVerification();
  }, [key, navigate]);

  if (status === 'verifying') {
    return (
      <div className="mx-auto max-w-md text-center">
        <div className="mb-6">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-100">
            <svg className="h-8 w-8 animate-spin text-blue-600" fill="none" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Verifying Your Email</h1>
          <p className="mt-2 text-gray-600">Please wait while we verify your email address...</p>
        </div>
      </div>
    );
  }

  if (status === 'success') {
    return (
      <div className="mx-auto max-w-md text-center">
        <div className="mb-6">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
            <svg
              className="h-8 w-8 text-green-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Email Verified!</h1>
          <p className="mt-2 text-gray-600">
            Your email address has been successfully verified. You can now log in to {SITE_NAME}!
          </p>
        </div>

        <div className="space-y-4">
          <div className="rounded-md bg-green-50 p-4">
            <p className="text-sm text-green-800">
              🎉 Welcome to {SITE_NAME}! You can now log in and start playing.
            </p>
          </div>

          <Button asChild className="w-full">
            <Link to="/login">Continue to Login</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md text-center">
      <div className="mb-6">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
          <svg
            className="h-8 w-8 text-red-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Verification Failed</h1>
        <p className="mt-2 text-gray-600">We couldn't verify your email address.</p>
      </div>

      <div className="space-y-4">
        <div className="rounded-md bg-red-50 p-4">
          <p className="text-sm text-red-800">{errorMessage}</p>
        </div>

        <div className="space-y-2">
          <Button asChild variant="outline" className="w-full">
            <Link to="/register/verify-email">Resend Verification Email</Link>
          </Button>

          <Button asChild variant="ghost" className="w-full">
            <Link to="/register">Back to Registration</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}

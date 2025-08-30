import { Link } from 'react-router-dom';
import { SITE_NAME } from '@/config';
import { Button } from '@/components/ui/button';
import { resendEmailVerification } from './api';
import { useState } from 'react';

export function EmailVerificationPendingPage() {
  const [isResending, setIsResending] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);
  const [resendError, setResendError] = useState('');

  const handleResendEmail = async () => {
    setIsResending(true);
    setResendError('');
    setResendSuccess(false);

    try {
      await resendEmailVerification();
      setResendSuccess(true);
    } catch (error) {
      setResendError(error instanceof Error ? error.message : 'Failed to resend email');
    } finally {
      setIsResending(false);
    }
  };

  return (
    <div className="mx-auto max-w-md text-center">
      <div className="mb-6">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-100">
          <svg
            className="h-8 w-8 text-blue-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 8l7.89 4.87a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Check Your Email</h1>
        <p className="mt-2 text-gray-600">
          We've sent a verification email to your address. Please click the link in the email to
          verify your account.
        </p>
      </div>

      <div className="space-y-4">
        <div className="rounded-md bg-blue-50 p-4">
          <h3 className="text-sm font-medium text-blue-800">What's next?</h3>
          <div className="mt-2 text-sm text-blue-700">
            <ul className="list-disc space-y-1 pl-5">
              <li>Check your email inbox</li>
              <li>Look in spam/junk folders if needed</li>
              <li>Click the verification link</li>
              <li>Return here to log in</li>
            </ul>
          </div>
        </div>

        <div className="space-y-2">
          {resendSuccess && (
            <div className="rounded-md bg-green-50 p-3 text-sm text-green-800">
              ✓ Verification email resent successfully!
            </div>
          )}

          {resendError && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-800">{resendError}</div>
          )}

          <Button
            variant="outline"
            onClick={handleResendEmail}
            disabled={isResending}
            className="w-full"
          >
            {isResending ? 'Sending...' : 'Resend Verification Email'}
          </Button>
        </div>

        <div className="pt-4">
          <Link to="/login" className="text-sm text-blue-600 hover:text-blue-500">
            Already verified? Sign in to {SITE_NAME}
          </Link>
        </div>
      </div>
    </div>
  );
}

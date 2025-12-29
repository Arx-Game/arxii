import { Link, useNavigate } from 'react-router-dom';
import { SITE_NAME } from '@/config';
import { Button } from '@/components/ui/button';
import { resendEmailVerification } from '@/evennia_replacements/api';
import { useState, useEffect } from 'react';
import { useAccount } from '@/store/hooks';

export function UnverifiedAccountPage() {
  const account = useAccount();
  const navigate = useNavigate();
  const [isResending, setIsResending] = useState(false);
  const [resendSuccess, setResendSuccess] = useState(false);
  const [resendError, setResendError] = useState('');

  // Redirect if already verified
  useEffect(() => {
    if (account?.email_verified) {
      navigate('/roster');
    }
  }, [account?.email_verified, navigate]);

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
    <div className="mx-auto max-w-2xl p-4">
      {/* Warning icon header */}
      <div className="mb-6">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-yellow-100">
          <svg
            className="h-8 w-8 text-yellow-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Email Verification Required</h1>
        <p className="mt-2 text-gray-600">
          Welcome to {SITE_NAME}, {account?.username}! Before you can apply for characters, you need
          to verify your email address.
        </p>
      </div>

      <div className="space-y-4">
        {/* What you CAN do */}
        <div className="rounded-md bg-blue-50 p-4">
          <h3 className="text-sm font-medium text-blue-800">What can I do while unverified?</h3>
          <div className="mt-2 text-sm text-blue-700">
            <ul className="list-disc space-y-1 pl-5">
              <li>Browse the character roster</li>
              <li>Read character backgrounds and lore</li>
              <li>View roleplay scenes</li>
              <li>Explore game features</li>
            </ul>
          </div>
        </div>

        {/* What requires verification */}
        <div className="rounded-md bg-yellow-50 p-4">
          <h3 className="text-sm font-medium text-yellow-800">What requires verification?</h3>
          <p className="mt-2 text-sm text-yellow-700">
            Applying for characters requires a verified email address. This helps prevent abuse and
            ensures we can contact you about your applications.
          </p>
        </div>

        {/* Resend email section */}
        <div className="rounded-md bg-gray-50 p-4">
          <h3 className="text-sm font-medium text-gray-800">Didn't receive the email?</h3>
          <p className="mt-2 text-sm text-gray-600">
            Check your spam folder, or request a new verification email to {account?.email}
          </p>
          <div className="mt-2 space-y-2">
            {resendSuccess && (
              <div className="rounded-md bg-green-50 p-3 text-sm text-green-800">
                ✓ Verification email resent to {account?.email}
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
        </div>

        {/* Links to browsable content */}
        <div className="space-y-2 pt-4">
          <Link
            to="/roster"
            className="block text-center text-sm text-blue-600 hover:text-blue-500"
          >
            Browse Character Roster →
          </Link>
          <Link
            to="/scenes"
            className="block text-center text-sm text-blue-600 hover:text-blue-500"
          >
            View Roleplay Scenes →
          </Link>
        </div>
      </div>
    </div>
  );
}

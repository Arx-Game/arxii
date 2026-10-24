import { useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { requestPasswordReset, validatePasswordResetKey, confirmPasswordReset } from './api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SubmitButton } from '@/components/SubmitButton';

export function PasswordResetRequestPage() {
  const [email, setEmail] = useState('');
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError('');
    try {
      await requestPasswordReset(email.trim());
      setSent(true);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : 'Could not request a reset link. Try again.'
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-bold text-foreground">Reset your password</h1>
      {sent ? (
        <div role="status" className="space-y-3">
          <h2 className="font-semibold">Check your email</h2>
          <p className="text-muted-foreground">
            If an account uses that address, we have sent a password reset link. Check your inbox
            and spam folder. If it does not arrive, contact staff for help.
          </p>
          <Button variant="outline" onClick={() => setSent(false)}>
            Try another address
          </Button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <p className="text-muted-foreground">Enter your account email to request a reset link.</p>
          <div className="space-y-1">
            <Label htmlFor="reset-email">Email</Label>
            <Input
              id="reset-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          {error && (
            <p role="alert" className="text-red-700 dark:text-red-400">
              {error}
            </p>
          )}
          <SubmitButton className="w-full" isLoading={pending}>
            Send reset link
          </SubmitButton>
        </form>
      )}
      <Link to="/login" className="block text-primary underline">
        Back to login
      </Link>
    </div>
  );
}

export function PasswordResetPage() {
  const { key } = useParams<{ key: string }>();
  const [keyState, setKeyState] = useState<'checking' | 'valid' | 'error'>('checking');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [pending, setPending] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setKeyState('checking');
    setComplete(false);
    setPassword('');
    setConfirmation('');
    setError('');
    if (!key) {
      setKeyState('error');
      setError('This reset link is missing its key. Request a new link.');
      return;
    }
    validatePasswordResetKey(key).then(
      () => {
        if (active) setKeyState('valid');
      },
      (error: unknown) => {
        if (!active) return;
        setKeyState('error');
        setError(error instanceof Error ? error.message : 'Could not check this reset link.');
      }
    );
    return () => {
      active = false;
    };
  }, [key]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!key || keyState !== 'valid') return;
    if (password !== confirmation) {
      setError('Passwords must match.');
      return;
    }
    setPending(true);
    setError('');
    try {
      await confirmPasswordReset({ key, password });
      setPassword('');
      setConfirmation('');
      setComplete(true);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : 'Could not reset your password. Try again.'
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm space-y-6">
      <h1 className="text-2xl font-bold text-foreground">
        {complete ? 'Password reset' : 'Choose a new password'}
      </h1>
      {complete ? (
        <div role="status" className="space-y-4">
          <p className="text-muted-foreground">
            Your password has been changed. You can now log in.
          </p>
          <Button asChild className="w-full">
            <Link to="/login">Continue to login</Link>
          </Button>
        </div>
      ) : (
        <>
          {keyState === 'checking' && <p role="status">Checking your reset link...</p>}
          {error && (
            <p role="alert" className="text-red-700 dark:text-red-400">
              {error}
            </p>
          )}
          {keyState === 'valid' && (
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="new-password">New password</Label>
                <Input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Use at least 8 characters. Avoid common or entirely numeric passwords.
                </p>
              </div>
              <div className="space-y-1">
                <Label htmlFor="confirm-password">Confirm new password</Label>
                <Input
                  id="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                />
              </div>
              <SubmitButton className="w-full" isLoading={pending}>
                Reset password
              </SubmitButton>
            </form>
          )}
          <Link to="/reset-password" className="block text-primary underline">
            Request a new reset link
          </Link>
          <Link to="/login" className="block text-primary underline">
            Back to login
          </Link>
        </>
      )}
    </div>
  );
}

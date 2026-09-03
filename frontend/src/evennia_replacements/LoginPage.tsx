import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useCompleteMfaLogin, useLogin } from './queries';
import { SITE_NAME } from '@/config';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SubmitButton } from '@/components/SubmitButton';
import { Button } from '@/components/ui/button';
import { fetchSocialProviders, initiateSocialLogin } from './api';

/** Only a same-origin, absolute path is a safe post-login redirect target, anything
 * else (a `//host` or `/\host` scheme-relative URL, an absolute URL with a scheme, a
 * relative path) falls back to '/'. */
function safeNext(value: string | null): string {
  if (value && value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/\\')) {
    return value;
  }
  return '/';
}

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const next = safeNext(searchParams.get('next'));
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [mfaStep, setMfaStep] = useState(false);
  const [code, setCode] = useState('');

  // Fetch available social auth providers
  const { data: providers = [] } = useQuery({
    queryKey: ['socialProviders'],
    queryFn: fetchSocialProviders,
  });

  const handleSocialLogin = (providerId: string) => {
    initiateSocialLogin(providerId, 'login');
  };

  const goToDestination = (accountData: { email_verified: boolean }) => {
    if (!accountData.email_verified) {
      navigate('/account/unverified');
    } else {
      navigate(next);
    }
  };

  const mutation = useLogin((result) => {
    if (result.kind === 'mfa_required') {
      setMfaStep(true);
      return;
    }
    goToDestination(result.account);
  });

  const mfa = useCompleteMfaLogin((account) => {
    goToDestination(account);
  });

  if (mfaStep) {
    return (
      <div className="mx-auto max-w-sm">
        <h1 className="mb-6 text-2xl font-bold">Login to {SITE_NAME}</h1>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            mfa.mutate(code);
          }}
          className="space-y-4"
        >
          <p className="text-sm text-muted-foreground">
            Enter the 6-digit code from your authenticator app, or one of your recovery codes.
          </p>
          <Label htmlFor="mfa-code">Authenticator code or recovery code</Label>
          <Input
            id="mfa-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <SubmitButton className="w-full" isLoading={mfa.isPending} disabled={!code}>
            Continue
          </SubmitButton>
          {mfa.isError && <p className="text-red-600">{mfa.error.message}</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-6 text-2xl font-bold">Login to {SITE_NAME}</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ login, password });
        }}
        className="space-y-4"
      >
        <Input
          type="text"
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          placeholder="Username or Email"
        />
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
        />
        <SubmitButton
          className="w-full"
          isLoading={mutation.isPending}
          disabled={!login || !password}
        >
          Log In
        </SubmitButton>
      </form>
      {mutation.isError && <p className="mt-4 text-red-600">Login failed. Please try again.</p>}
      {providers.length > 0 && (
        <div className="mt-6 space-y-2">
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-background px-2 text-muted-foreground">Or continue with</span>
            </div>
          </div>
          {providers.map((provider) => (
            <Button
              key={provider.id}
              variant="outline"
              className="w-full"
              onClick={() => handleSocialLogin(provider.id)}
            >
              Log in with {provider.name}
            </Button>
          ))}
        </div>
      )}
      <p className="mt-4 text-center text-sm">
        Don't have an account?{' '}
        <Link to="/register" className="text-blue-500 hover:underline">
          Register
        </Link>
        .
      </p>
    </div>
  );
}

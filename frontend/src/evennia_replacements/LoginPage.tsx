import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useLogin } from './queries';
import { SITE_NAME } from '@/config';
import { Input } from '@/components/ui/input';
import { SubmitButton } from '@/components/SubmitButton';

export function LoginPage() {
  const navigate = useNavigate();
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const mutation = useLogin((accountData) => {
    // Check if email is verified
    if (!accountData.email_verified) {
      navigate('/account/unverified');
    } else {
      navigate('/');
    }
  });

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

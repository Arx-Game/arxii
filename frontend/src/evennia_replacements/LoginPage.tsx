import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useLogin } from './queries';
import { SITE_NAME } from '@/config';
import { Input } from '@/components/ui/input';
import { SubmitButton } from '@/components/SubmitButton';

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const mutation = useLogin(() => {
    navigate('/');
  });

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-6 text-2xl font-bold">Login to {SITE_NAME}</h1>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ username, password });
        }}
        className="space-y-4"
      >
        <Input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Username"
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
          disabled={!username || !password}
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

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLogin } from './queries';
import { SITE_NAME } from '../config';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';

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
        <Button type="submit" className="w-full">
          Log In
        </Button>
      </form>
      {mutation.isError && <p className="mt-4 text-red-600">Login failed. Please try again.</p>}
    </div>
  );
}

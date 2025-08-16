import { useNavigate } from 'react-router-dom';
import { useRegister } from './queries';
import { SITE_NAME } from '../config';
import { Input } from '../components/ui/input';
import { SubmitButton } from '../components/SubmitButton';
import { Button } from '../components/ui/button';
import { useForm } from 'react-hook-form';
import { checkUsername, checkEmail } from './api';

const providers = ['Google', 'Facebook', 'Instagram', 'TikTok', 'Discord'];

type FormValues = {
  username: string;
  email: string;
  password: string;
};

export function RegisterPage() {
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm<FormValues>({ mode: 'onBlur' });
  const mutation = useRegister(() => {
    navigate('/');
  });
  const onSubmit = handleSubmit((data) => mutation.mutate(data));

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-6 text-2xl font-bold">Register for {SITE_NAME}</h1>
      <form onSubmit={onSubmit} className="space-y-4">
        <Input
          placeholder="Username"
          {...register('username', {
            required: 'Username is required',
            validate: async (value) => (await checkUsername(value)) || 'Username already taken',
          })}
        />
        {errors.username && <p className="text-sm text-red-600">{errors.username.message}</p>}
        <Input
          placeholder="Email"
          type="email"
          {...register('email', {
            required: 'Email is required',
            validate: async (value) => (await checkEmail(value)) || 'Email already taken',
          })}
        />
        {errors.email && <p className="text-sm text-red-600">{errors.email.message}</p>}
        <Input
          type="password"
          placeholder="Password"
          {...register('password', {
            required: 'Password is required',
          })}
        />
        {errors.password && <p className="text-sm text-red-600">{errors.password.message}</p>}
        <SubmitButton className="w-full" isLoading={mutation.isPending} disabled={!isValid}>
          Register
        </SubmitButton>
      </form>
      {mutation.isError && (
        <p className="mt-4 text-red-600">Registration failed. Please try again.</p>
      )}
      <div className="mt-6 space-y-2">
        {providers.map((name) => (
          <Button
            key={name}
            variant="outline"
            className="w-full"
            onClick={() => alert('Coming soon')}
          >
            Sign up with {name}
          </Button>
        ))}
      </div>
    </div>
  );
}

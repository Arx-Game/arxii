import { useNavigate } from 'react-router-dom';
import { useRegister } from './queries';
import { SITE_NAME } from '@/config';
import { Input } from '@/components/ui/input';
import { SubmitButton } from '@/components/SubmitButton';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { useForm } from 'react-hook-form';
import { checkUsername, checkEmail } from './api';

const providers = ['Google', 'Facebook', 'Instagram', 'TikTok', 'Discord'];

type FormValues = {
  username: string;
  email: string;
  password1: string;
  password2: string;
};

export function RegisterPage() {
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm<FormValues>({ mode: 'onBlur' });
  const mutation = useRegister((result, email) => {
    if (result.emailVerificationRequired) {
      // Show success message with email verification instructions
      navigate('/register/verify-email', { state: { email } });
    } else {
      // User is logged in, go to home
      navigate('/');
    }
  });
  const onSubmit = handleSubmit((data) => {
    // Transform form data to API format
    const apiData = {
      username: data.username,
      email: data.email,
      password: data.password1, // Send single password field
    };
    mutation.mutate(apiData);
  });

  return (
    <div className="mx-auto max-w-sm">
      <h1 className="mb-6 text-2xl font-bold">Register for {SITE_NAME}</h1>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1">
          <Label htmlFor="username">Username</Label>
          <Input
            id="username"
            placeholder="Username"
            {...register('username', {
              required: 'Username is required',
              validate: async (value) => (await checkUsername(value)) || 'Username already taken',
            })}
          />
          {errors.username && <p className="text-sm text-red-600">{errors.username.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            placeholder="Email"
            type="email"
            {...register('email', {
              required: 'Email is required',
              validate: async (value) => (await checkEmail(value)) || 'Email already taken',
            })}
          />
          {errors.email && <p className="text-sm text-red-600">{errors.email.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="password1">Password</Label>
          <Input
            id="password1"
            type="password"
            placeholder="Password"
            {...register('password1', {
              required: 'Password is required',
            })}
          />
          {errors.password1 && <p className="text-sm text-red-600">{errors.password1.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="password2">Confirm Password</Label>
          <Input
            id="password2"
            type="password"
            placeholder="Confirm Password"
            {...register('password2', {
              required: 'Password confirmation is required',
              validate: (value, formValues) =>
                value === formValues.password1 || 'Passwords must match',
            })}
          />
          {errors.password2 && <p className="text-sm text-red-600">{errors.password2.message}</p>}
        </div>
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

import { AccountData, SignupResponse, StatusData } from './types';
import { getCookie } from '@/lib/utils';

function getCSRFToken(): string {
  return getCookie('csrftoken') || '';
}

export function apiFetch(url: string, options: RequestInit = {}) {
  const method = options.method?.toUpperCase() ?? 'GET';
  const headers = new Headers(options.headers);

  if (method !== 'GET') {
    headers.set('Content-Type', 'application/json');
    headers.set('X-CSRFToken', getCSRFToken());
  }

  return fetch(url, {
    credentials: 'include',
    ...options,
    headers,
  });
}

export async function fetchStatus(): Promise<StatusData> {
  const res = await apiFetch('/api/status/');
  if (!res.ok) {
    throw new Error('Failed to load status');
  }
  return res.json();
}

export async function fetchAccount(): Promise<AccountData | null> {
  const res = await apiFetch('/api/user/');
  if (!res.ok) {
    throw new Error('Failed to load account');
  }

  const text = await res.text();
  if (!text.trim()) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    console.error('Failed to parse account response:', text);
    throw new Error('Invalid account response format');
  }
}

export async function postLogin(data: { login: string; password: string }): Promise<AccountData> {
  // Django-allauth headless API expects 'username' or 'email' fields, not 'login'
  // Transform the login field to the appropriate field type
  const isEmail = data.login.includes('@');
  const requestData = isEmail
    ? { email: data.login, password: data.password }
    : { username: data.login, password: data.password };

  const res = await apiFetch('/api/auth/browser/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(requestData),
  });
  if (!res.ok) {
    const errorData = await res.json();
    console.error('Login error response:', res.status, errorData);

    // Handle different error response formats
    if (errorData.detail) {
      throw new Error(errorData.detail);
    }

    // Check for errors array (allauth validation errors)
    if (errorData.errors && Array.isArray(errorData.errors)) {
      const errorMessages = errorData.errors
        .map((err: { message?: string }) => err.message)
        .filter(Boolean)
        .join(', ');
      if (errorMessages) {
        throw new Error(errorMessages);
      }
    }

    // Fallback to generic message
    throw new Error('Login failed');
  }

  // Login successful, now fetch the user data in our expected format
  const userRes = await apiFetch('/api/user/');
  if (!userRes.ok) {
    throw new Error('Failed to load user data after login');
  }

  return userRes.json();
}

export async function postLogout(): Promise<void> {
  await apiFetch('/api/auth/browser/v1/auth/logout', { method: 'POST' });
}

export async function postRegister(data: {
  username: string;
  password: string;
  email: string;
}): Promise<{ success: true; emailVerificationRequired: boolean }> {
  const res = await apiFetch('/api/auth/browser/v1/auth/signup', {
    method: 'POST',
    body: JSON.stringify(data),
  });

  if (res.status === 401) {
    // 401 with email verification flow means registration succeeded but email verification required
    const responseData: SignupResponse = await res.json();
    const hasEmailVerificationFlow = responseData.data?.flows?.some(
      (flow) => flow.id === 'verify_email' && flow.is_pending
    );

    if (hasEmailVerificationFlow) {
      return { success: true, emailVerificationRequired: true };
    }
  }

  if (!res.ok) {
    const errorData = await res.json();
    console.error('Registration error response:', res.status, errorData);

    // Handle different error response formats
    // allauth headless sometimes returns minimal {status: 409} responses
    if (errorData.detail) {
      throw new Error(errorData.detail);
    }

    // Check for errors array (allauth validation errors)
    if (errorData.errors && Array.isArray(errorData.errors)) {
      const errorMessages = errorData.errors
        .map((err: { message?: string }) => err.message)
        .filter(Boolean)
        .join(', ');
      if (errorMessages) {
        throw new Error(errorMessages);
      }
    }

    // Provide specific message for 409 Conflict (duplicate username/email)
    if (res.status === 409) {
      throw new Error('Username or email already exists');
    }

    // Fallback to generic message
    throw new Error('Registration failed');
  }

  // Registration completed without email verification required
  return { success: true, emailVerificationRequired: false };
}

export async function checkUsername(username: string): Promise<boolean> {
  const res = await apiFetch(
    `/api/register/availability/?username=${encodeURIComponent(username)}`
  );
  if (!res.ok) {
    throw new Error('Username check failed');
  }
  const data = await res.json();
  return data.username;
}

export async function checkEmail(email: string): Promise<boolean> {
  const res = await apiFetch(`/api/register/availability/?email=${encodeURIComponent(email)}`);
  if (!res.ok) {
    throw new Error('Email check failed');
  }
  const data = await res.json();
  return data.email;
}

// Password reset functionality
export async function requestPasswordReset(email: string): Promise<void> {
  const res = await apiFetch('/api/auth/browser/v1/auth/password/request', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Password reset request failed');
  }
}

export async function confirmPasswordReset(data: { key: string; password: string }): Promise<void> {
  const res = await apiFetch('/api/auth/browser/v1/auth/password/reset', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Password reset confirmation failed');
  }
}

export async function changePassword(data: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  const res = await apiFetch('/api/auth/browser/v1/auth/password/change', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Password change failed');
  }
}

// Email verification functionality
export async function verifyEmail(key: string): Promise<void> {
  const res = await apiFetch('/api/auth/browser/v1/auth/email/verify', {
    method: 'POST',
    body: JSON.stringify({ key }),
  });
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Email verification failed');
  }
}

export async function resendEmailVerification(email?: string): Promise<void> {
  const res = await apiFetch('/api/auth/browser/v1/auth/email/request', {
    method: 'POST',
    body: JSON.stringify(email ? { email } : {}),
  });
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Failed to resend verification email');
  }
}

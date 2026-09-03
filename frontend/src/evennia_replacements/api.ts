import {
  AccountData,
  ConnectedSocialAccount,
  LoginResult,
  RegistrationStatus,
  SignupResponse,
  SocialProvider,
} from './types';
import { getCookie } from '@/lib/utils';

function getCSRFToken(): string {
  return getCookie('csrftoken') || '';
}

export function apiFetch(url: string, options: RequestInit = {}) {
  const method = options.method?.toUpperCase() ?? 'GET';
  const headers = new Headers(options.headers);

  if (method !== 'GET') {
    // A FormData body must NOT be labeled application/json — fetch derives the
    // correct multipart Content-Type (with boundary) only when none is set.
    // Forcing JSON here made every multipart upload a guaranteed DRF 400.
    if (!(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }
    headers.set('X-CSRFToken', getCSRFToken());
  }

  return fetch(url, {
    credentials: 'include',
    ...options,
    headers,
  });
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

export async function postLogin(data: { login: string; password: string }): Promise<LoginResult> {
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
    // A 500 returns Django's HTML error page — never feed that to res.json() (#3193)
    const errorData = (await res.json().catch(() => null)) ?? {};
    console.error('Login error response:', res.status, errorData);

    // A 401 whose pending flows include mfa_authenticate means the password
    // was correct and a second factor is needed, not that login failed.
    if (
      res.status === 401 &&
      (errorData as SignupResponse).data?.flows?.some(
        (f) => f.id === 'mfa_authenticate' && f.is_pending
      )
    ) {
      return { kind: 'mfa_required' };
    }

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

    if (res.status >= 500) {
      throw new Error('The server hit an error during login. Please try again shortly.');
    }

    // Fallback to generic message
    throw new Error('Login failed');
  }

  // Login successful, now fetch the user data in our expected format
  const userRes = await apiFetch('/api/user/');
  if (!userRes.ok) {
    throw new Error('Failed to load user data after login');
  }

  return { kind: 'ok', account: await userRes.json() };
}

/** Completes a login that stopped at the 2FA step (#3591): submits the
 * authenticator/recovery code to allauth's headless 2FA endpoint directly
 * (rather than importing `@/account/api`'s `mfaAuthenticate`, which itself
 * imports `apiFetch` from this module, so a static import here would be a
 * module cycle), then fetches the now-authenticated user. */
export async function completeMfaLogin(code: string): Promise<AccountData> {
  const res = await apiFetch('/api/auth/browser/v1/auth/2fa/authenticate', {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
  if (!res.ok) {
    // A 500 returns Django's HTML error page, never feed that to res.json() (#3193)
    const errorData = (await res.json().catch(() => null)) ?? {};
    console.error('2FA authenticate error response:', res.status, errorData);

    if (errorData.errors && Array.isArray(errorData.errors)) {
      const errorMessages = errorData.errors
        .map((err: { message?: string }) => err.message)
        .filter(Boolean)
        .join(', ');
      if (errorMessages) {
        throw new Error(errorMessages);
      }
    }

    throw new Error('That code was not accepted.');
  }

  const userRes = await apiFetch('/api/user/');
  if (!userRes.ok) {
    throw new Error('Failed to load user data after login');
  }
  return userRes.json();
}

export async function postLogout(): Promise<void> {
  await apiFetch('/api/auth/browser/v1/auth/logout', { method: 'POST' });
}

/** True when a 401 signup response's payload indicates registration succeeded
 * but email verification is still pending, rather than an actual auth failure. */
function hasPendingEmailVerificationFlow(responseData: SignupResponse | null): boolean {
  return (
    responseData?.data?.flows?.some((flow) => flow.id === 'verify_email' && flow.is_pending) ??
    false
  );
}

/** Builds the Error to throw for a failed /auth/signup response. Tries, in
 * order: the allauth `detail` field, aggregated `errors` array messages
 * (allauth validation errors), a 409-specific duplicate-account message, a
 * 5xx-specific message, then a generic fallback. */
async function buildRegistrationError(res: Response): Promise<Error> {
  // A 500 returns Django's HTML error page — never feed that to res.json() (#3193)
  const errorData = (await res.json().catch(() => null)) ?? {};
  console.error('Registration error response:', res.status, errorData);

  // Handle different error response formats
  // allauth headless sometimes returns minimal {status: 409} responses
  if (errorData.detail) {
    return new Error(errorData.detail);
  }

  // Check for errors array (allauth validation errors)
  if (errorData.errors && Array.isArray(errorData.errors)) {
    const errorMessages = errorData.errors
      .map((err: { message?: string }) => err.message)
      .filter(Boolean)
      .join(', ');
    if (errorMessages) {
      return new Error(errorMessages);
    }
  }

  // Provide specific message for 409 Conflict (duplicate username/email)
  if (res.status === 409) {
    return new Error('Username or email already exists');
  }

  if (res.status >= 500) {
    return new Error(
      'The server hit an error during registration. Your account may still have been ' +
        'created - try logging in, and contact staff if you cannot.'
    );
  }

  // Fallback to generic message
  return new Error('Registration failed');
}

export async function postRegister(data: {
  username: string;
  password: string;
  email: string;
  /** Invite-only registration (#3054) — omitted from the request body when unset. */
  inviteToken?: string;
}): Promise<{ success: true; emailVerificationRequired: boolean }> {
  const body: { username: string; email: string; password: string; invite_token?: string } = {
    username: data.username,
    email: data.email,
    password: data.password,
  };
  if (data.inviteToken) {
    body.invite_token = data.inviteToken;
  }
  const res = await apiFetch('/api/auth/browser/v1/auth/signup', {
    method: 'POST',
    body: JSON.stringify(body),
  });

  if (res.status === 401) {
    // 401 with email verification flow means registration succeeded but email verification required
    const responseData: SignupResponse | null = await res.json().catch(() => null);
    if (hasPendingEmailVerificationFlow(responseData)) {
      return { success: true, emailVerificationRequired: true };
    }
  }

  if (!res.ok) {
    throw await buildRegistrationError(res);
  }

  // Registration completed without email verification required
  return { success: true, emailVerificationRequired: false };
}

/** Public, unauthenticated (#3054) — used by RegisterPage to decide whether to show
 * the invite-only notice instead of the signup form. Never enumerates invites. */
export async function fetchRegistrationStatus(): Promise<RegistrationStatus> {
  const res = await apiFetch('/api/registration/status/');
  if (!res.ok) {
    throw new Error('Failed to load registration status');
  }
  return res.json();
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

// Social authentication functionality
export async function fetchSocialProviders(): Promise<SocialProvider[]> {
  const res = await apiFetch('/api/social-providers/');
  if (!res.ok) {
    throw new Error('Failed to load social providers');
  }
  const data = await res.json();
  return data.providers;
}

export async function initiateSocialLogin(
  providerId: string,
  process: 'login' | 'connect' = 'login'
): Promise<void> {
  // Get the callback URL - this is where the user returns after OAuth
  const callbackUrl = `${window.location.origin}/auth/callback`;

  // The allauth headless redirect endpoint expects form data
  const formData = new URLSearchParams();
  formData.append('provider', providerId);
  formData.append('callback_url', callbackUrl);
  formData.append('process', process);

  // For social auth, we need to redirect the browser to the provider
  // Build the URL and redirect manually
  const res = await fetch('/api/auth/browser/v1/auth/provider/redirect', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-CSRFToken': getCSRFToken(),
    },
    body: formData.toString(),
    redirect: 'manual', // Don't auto-follow redirects
  });

  // allauth returns a redirect response with the provider URL
  if (res.type === 'opaqueredirect' || res.status === 302) {
    // The redirect URL is in the Location header, but we can't read it due to CORS
    // Instead, we need to use a different approach - let the browser handle it
    // by navigating directly
    window.location.href = `/api/auth/browser/v1/auth/provider/redirect?provider=${providerId}&callback_url=${encodeURIComponent(callbackUrl)}&process=${process}`;
    return;
  }

  // Try to get redirect URL from response body
  if (res.ok) {
    const data = await res.json();
    if (data.data?.url) {
      window.location.href = data.data.url;
      return;
    }
  }

  throw new Error('Failed to initiate social login');
}

// Account linking - fetch connected social accounts
export async function fetchConnectedAccounts(): Promise<ConnectedSocialAccount[]> {
  const res = await apiFetch('/api/auth/browser/v1/account/providers');
  if (!res.ok) {
    throw new Error('Failed to load connected accounts');
  }
  const data = await res.json();
  return data.data || [];
}

// Account linking - disconnect a social account
export async function disconnectSocialAccount(accountId: number): Promise<void> {
  const res = await apiFetch('/api/auth/browser/v1/account/providers', {
    method: 'DELETE',
    body: JSON.stringify({ account: accountId }),
  });
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Failed to disconnect account');
  }
}

/**
 * Append a querystring to a URL, or nothing when there is none.
 *
 * Every list endpoint spelled this out as a nested template literal, which is
 * the nesting the flatness ruling rejects, repeated across a dozen files (#3548).
 */
export function withQuery(base: string, search: URLSearchParams | string): string {
  const qs = typeof search === 'string' ? search : search.toString();
  return qs ? `${base}?${qs}` : base;
}

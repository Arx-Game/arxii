/**
 * Account settings over allauth headless (#3591): email, password, reauthentication, 2FA.
 *
 * Every function talks to a route allauth already mounts under /api/auth/browser/v1/ and
 * parses its envelope `{status, data, meta, errors}`. A 401 whose flows include
 * `reauthenticate` / `mfa_reauthenticate` is a challenge, not a failure: it is thrown as
 * `ReauthenticationRequiredError` so `useReauthGuard` can ask for the password (or code)
 * and retry once.
 *
 * Reauthentication itself is mounted under `auth/`, not `account/`, unlike every other
 * route here (allauth's own route table).
 */
import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';
import type {
  AuthenticatorInfo,
  AuthFlow,
  EmailAddressInfo,
  HeadlessEnvelope,
  RecoveryCodes,
  TotpSetup,
} from './types';

const BASE = '/api/auth/browser/v1';
const SECURITY_URL = '/api/account/security-settings/';

export type AccountSecuritySettings = components['schemas']['AccountSecuritySettings'];

export class ReauthenticationRequiredError extends Error {
  flows: string[];
  constructor(flows: string[]) {
    super('Please confirm it is you to continue.');
    this.name = 'ReauthenticationRequiredError';
    this.flows = flows;
  }
}

const REAUTH_FLOWS = new Set(['reauthenticate', 'mfa_reauthenticate']);

/** True when a headless body carries a pending flow with this id. */
export function pendingFlow(
  body: { data?: { flows?: AuthFlow[] } } | null | undefined,
  id: string
) {
  return body?.data?.flows?.some((f) => f.id === id && f.is_pending === true) ?? false;
}

async function readEnvelope<T>(res: Response): Promise<HeadlessEnvelope<T>> {
  // A 500 returns Django's HTML error page; never feed that to res.json() (#3193).
  return ((await res.json().catch(() => null)) ?? { status: res.status }) as HeadlessEnvelope<T>;
}

function messageFrom(body: HeadlessEnvelope, fallback: string): string {
  const messages = (body.errors ?? []).map((e) => e.message).filter(Boolean);
  return messages.length ? messages.join(' ') : fallback;
}

async function headless<T>(
  path: string,
  init: RequestInit,
  fallback: string
): Promise<HeadlessEnvelope<T>> {
  const res = await apiFetch(`${BASE}${path}`, init);
  const body = await readEnvelope<T>(res);
  if (res.status === 401 && body.meta?.is_authenticated) {
    const flows = (body as HeadlessEnvelope<{ flows?: AuthFlow[] }>).data?.flows ?? [];
    const ids = flows.map((f) => f.id).filter((id) => REAUTH_FLOWS.has(id));
    if (ids.length) throw new ReauthenticationRequiredError(ids);
  }
  if (!res.ok) throw new Error(messageFrom(body, fallback));
  return body;
}

const json = (method: string, payload?: unknown): RequestInit => ({
  method,
  body: payload === undefined ? undefined : JSON.stringify(payload),
});

// Email ---------------------------------------------------------------------

export async function fetchEmailAddresses(): Promise<EmailAddressInfo[]> {
  const body = await headless<EmailAddressInfo[]>(
    '/account/email',
    {},
    'Could not load your email address.'
  );
  return body.data ?? [];
}

export async function requestEmailChange(email: string): Promise<EmailAddressInfo[]> {
  const body = await headless<EmailAddressInfo[]>(
    '/account/email',
    json('POST', { email }),
    'Could not start the email change.'
  );
  return body.data ?? [];
}

export async function resendEmailChangeVerification(email: string): Promise<void> {
  await headless(
    '/account/email',
    json('PUT', { email }),
    'Could not resend the verification mail.'
  );
}

export async function cancelEmailChange(email: string): Promise<EmailAddressInfo[]> {
  const body = await headless<EmailAddressInfo[]>(
    '/account/email',
    json('DELETE', { email }),
    'Could not cancel the change.'
  );
  return body.data ?? [];
}

// Password ------------------------------------------------------------------

export async function changePassword(data: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  await headless('/account/password/change', json('POST', data), 'Password change failed.');
}

// Reauthentication ------------------------------------------------------------

export async function reauthenticateWithPassword(password: string): Promise<void> {
  await headless(
    '/auth/reauthenticate',
    json('POST', { password }),
    'That password was not accepted.'
  );
}

export async function reauthenticateWithCode(code: string): Promise<void> {
  await headless('/auth/2fa/reauthenticate', json('POST', { code }), 'That code was not accepted.');
}

// Two-factor ------------------------------------------------------------------

export async function fetchAuthenticators(): Promise<AuthenticatorInfo[]> {
  const body = await headless<AuthenticatorInfo[]>(
    '/account/authenticators',
    {},
    'Could not load two-factor status.'
  );
  return body.data ?? [];
}

/** allauth answers 404 with the secret in `meta` while no TOTP authenticator exists. */
export async function fetchTotpSetup(): Promise<TotpSetup> {
  const res = await apiFetch(`${BASE}/account/authenticators/totp`);
  const body = await readEnvelope<AuthenticatorInfo>(res);
  if (res.status === 404 && body.meta?.secret && body.meta?.totp_url) {
    return { secret: String(body.meta.secret), totp_url: String(body.meta.totp_url) };
  }
  if (res.ok) throw new Error('Two-factor authentication is already on.');
  throw new Error(messageFrom(body, 'Could not start two-factor setup.'));
}

export async function activateTotp(code: string): Promise<AuthenticatorInfo> {
  const body = await headless<AuthenticatorInfo>(
    '/account/authenticators/totp',
    json('POST', { code }),
    'That code was not accepted.'
  );
  return body.data as AuthenticatorInfo;
}

export async function deactivateTotp(): Promise<void> {
  await headless(
    '/account/authenticators/totp',
    json('DELETE'),
    'Could not turn two-factor authentication off.'
  );
}

export async function fetchRecoveryCodes(): Promise<RecoveryCodes> {
  const body = await headless<RecoveryCodes>(
    '/account/authenticators/recovery-codes',
    {},
    'Could not load recovery codes.'
  );
  return body.data as RecoveryCodes;
}

export async function regenerateRecoveryCodes(): Promise<RecoveryCodes> {
  const body = await headless<RecoveryCodes>(
    '/account/authenticators/recovery-codes',
    json('POST', {}),
    'Could not regenerate recovery codes.'
  );
  return body.data as RecoveryCodes;
}

/** Second step of login for a 2FA account. Accepts a TOTP code or a recovery code. */
export async function mfaAuthenticate(code: string): Promise<void> {
  const res = await apiFetch(`${BASE}/auth/2fa/authenticate`, json('POST', { code }));
  const body = await readEnvelope(res);
  if (!res.ok) throw new Error(messageFrom(body, 'That code was not accepted.'));
}

// Security settings (ours) -----------------------------------------------------

export async function fetchSecuritySettings(): Promise<AccountSecuritySettings> {
  const res = await apiFetch(SECURITY_URL);
  if (!res.ok) throw new Error('Could not load security settings.');
  return res.json() as Promise<AccountSecuritySettings>;
}

export async function setBlockTelnetLoginWith2fa(value: boolean): Promise<AccountSecuritySettings> {
  const res = await apiFetch(SECURITY_URL, json('PATCH', { block_telnet_login_with_2fa: value }));
  if (!res.ok) throw new Error('Could not update the telnet setting.');
  return res.json() as Promise<AccountSecuritySettings>;
}

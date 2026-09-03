import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ReauthenticationRequiredError,
  changePassword,
  fetchEmailAddresses,
  fetchTotpSetup,
  pendingFlow,
  reauthenticateWithCode,
  reauthenticateWithPassword,
  requestEmailChange,
} from '../api';

function mockFetch(status: number, body: unknown) {
  const res = {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  } as unknown as Response;
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res));
  return vi.mocked(fetch);
}

afterEach(() => vi.unstubAllGlobals());

describe('account api', () => {
  it('lists email addresses from the envelope', async () => {
    mockFetch(200, { status: 200, data: [{ email: 'a@b.c', verified: true, primary: true }] });
    expect(await fetchEmailAddresses()).toEqual([
      { email: 'a@b.c', verified: true, primary: true },
    ]);
  });

  it('throws ReauthenticationRequiredError on a reauth 401', async () => {
    mockFetch(401, {
      status: 401,
      data: { flows: [{ id: 'reauthenticate' }, { id: 'mfa_reauthenticate' }] },
      meta: { is_authenticated: true },
    });
    await expect(requestEmailChange('new@b.c')).rejects.toBeInstanceOf(
      ReauthenticationRequiredError
    );
    await expect(requestEmailChange('new@b.c')).rejects.toMatchObject({
      flows: ['reauthenticate', 'mfa_reauthenticate'],
    });
  });

  it('surfaces allauth field errors as a readable message', async () => {
    mockFetch(400, {
      status: 400,
      errors: [
        {
          message: 'Please type your current password.',
          code: 'enter_current_password',
          param: 'current_password',
        },
      ],
    });
    await expect(changePassword({ current_password: 'x', new_password: 'y' })).rejects.toThrow(
      'Please type your current password.'
    );
  });

  it('posts the password change to the account route', async () => {
    const f = mockFetch(200, { status: 200, data: {}, meta: { is_authenticated: true } });
    await changePassword({ current_password: 'old', new_password: 'new' });
    expect(f.mock.calls[0][0]).toBe('/api/auth/browser/v1/account/password/change');
  });

  it('reads the TOTP setup from the 404 envelope meta', async () => {
    mockFetch(404, { status: 404, meta: { secret: 'S', totp_url: 'otpauth://totp/x' } });
    expect(await fetchTotpSetup()).toEqual({ secret: 'S', totp_url: 'otpauth://totp/x' });
  });

  it('pendingFlow finds a pending flow by id', () => {
    expect(
      pendingFlow(
        { data: { flows: [{ id: 'mfa_authenticate', is_pending: true }] } },
        'mfa_authenticate'
      )
    ).toBe(true);
    expect(pendingFlow({ data: { flows: [{ id: 'mfa_authenticate' }] } }, 'mfa_authenticate')).toBe(
      false
    );
    expect(pendingFlow(null, 'mfa_authenticate')).toBe(false);
  });

  it('posts password reauthentication to the auth route, not account', async () => {
    const f = mockFetch(200, { status: 200, data: {}, meta: { is_authenticated: true } });
    await reauthenticateWithPassword('secret');
    expect(f.mock.calls[0][0]).toBe('/api/auth/browser/v1/auth/reauthenticate');
  });

  it('posts code reauthentication to the 2fa auth route, not account', async () => {
    const f = mockFetch(200, { status: 200, data: {}, meta: { is_authenticated: true } });
    await reauthenticateWithCode('123456');
    expect(f.mock.calls[0][0]).toBe('/api/auth/browser/v1/auth/2fa/reauthenticate');
  });
});

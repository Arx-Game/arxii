/** Shapes returned by allauth headless (#3591). Hand-rolled: headless is not in the OpenAPI schema. */

export interface EmailAddressInfo {
  email: string;
  verified: boolean;
  primary: boolean;
}

export type AuthenticatorType = 'totp' | 'recovery_codes';

export interface AuthenticatorInfo {
  type: AuthenticatorType;
  created_at: number;
  last_used_at: number | null;
  total_code_count?: number;
  unused_code_count?: number;
}

export interface TotpSetup {
  secret: string;
  totp_url: string;
}

export interface RecoveryCodes extends AuthenticatorInfo {
  type: 'recovery_codes';
  unused_codes: string[];
}

/** allauth headless response envelope. */
export interface HeadlessEnvelope<T = unknown> {
  status: number;
  data?: T;
  meta?: Record<string, unknown> & { is_authenticated?: boolean };
  errors?: { message: string; code: string; param?: string }[];
}

export interface AuthFlow {
  id: string;
  is_pending?: boolean;
}

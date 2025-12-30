import type { AccountData } from '@/evennia_replacements/types';

export const mockAccount: AccountData = {
  id: 1,
  username: 'tester',
  display_name: 'Tester',
  last_login: null,
  email: 'tester@test.com',
  email_verified: true,
  can_create_characters: true,
  is_staff: false,
};

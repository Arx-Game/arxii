import type { AccountData } from '@/evennia_replacements/types';

export const mockAccount: AccountData = {
  id: 1,
  username: 'tester',
  display_name: 'Tester',
  last_login: null,
  email: 'tester@test.com',
  email_verified: true,
  can_create_characters: true,
  character_slots: { total: 4, used: 0, activity_total: 1, activity_used: 0, holders: [] },
  is_staff: false,
  is_gm: false,
  available_characters: [],
  pending_applications: [],
  selected_entry_id: null,
  selected_entry: null,
};

export const mockStaffAccount: AccountData = {
  id: 2,
  username: 'staffuser',
  display_name: 'Staff User',
  last_login: null,
  email: 'staff@test.com',
  email_verified: true,
  can_create_characters: true,
  character_slots: { total: null, used: 0, activity_total: 1, activity_used: 0, holders: [] },
  is_staff: true,
  is_gm: false,
  available_characters: [],
  pending_applications: [],
  selected_entry_id: null,
  selected_entry: null,
};

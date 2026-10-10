/**
 * Staff edit mode on the sheet (#3988): the toggle is staff-only, a field saves and
 * cancels, an empty field keeps a slot, and a past version restores. Group fit
 * (#4229): ties are declared on a searched character, covenants and bonds post one
 * change each, and a waiting label and a bond's band warning show on their rows.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CharacterSheetPayload, CharacterSheetStaffEdit } from '@/character_sheets/api';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SheetPanel } from '../SheetPanel';
import { StaffEditProvider, StaffEditToggle } from '../StaffEdit';

const patchStaffEdit = vi.fn();
const restoreProfileTextVersion = vi.fn();
const fetchProfileTextVersions = vi.fn();
const fetchStaffOptions = vi.fn();
const runStaffRowAction = vi.fn();
const fetchStaffMagicOptions = vi.fn();
const fetchStaffEstateOptions = vi.fn();
const fetchStaffGroupOptions = vi.fn();

vi.mock('@/character_sheets/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/character_sheets/api')>();
  return {
    ...actual,
    patchStaffEdit: (...args: unknown[]) => patchStaffEdit(...args),
    restoreProfileTextVersion: (...args: unknown[]) => restoreProfileTextVersion(...args),
    fetchStaffOptions: (...args: unknown[]) => fetchStaffOptions(...args),
    runStaffRowAction: (...args: unknown[]) => runStaffRowAction(...args),
    fetchStaffMagicOptions: (...args: unknown[]) => fetchStaffMagicOptions(...args),
    fetchStaffEstateOptions: (...args: unknown[]) => fetchStaffEstateOptions(...args),
    fetchStaffGroupOptions: (...args: unknown[]) => fetchStaffGroupOptions(...args),
  };
});
vi.mock('@/sheet_update_requests/api', () => ({
  fetchProfileTextVersions: (...args: unknown[]) => fetchProfileTextVersions(...args),
}));

const STORED: CharacterSheetStaffEdit = {
  rows: {
    stats: {},
    skills: {},
    specializations: {},
    distinctions: [],
    form: {},
    markings: [],
    beginnings: null,
    path: null,
    class_level: null,
    public_being: null,
    secret_being: null,
    has_vitals: true,
    has_gift: true,
    has_aura: false,
    kin_node: null,
    residences: [],
    properties: [],
    reputations: [],
    personas: [],
    titles: [],
    noble_titles: [],
    ties: [],
    covenant_roles: [],
    mentor_bonds: [],
  },
  prose: {
    description: '',
    background: 'Raised at the quay.',
    concept: '',
    real_concept: '',
    quote: '',
    never_do: '',
    protect: '',
    fear: '',
    obituary: '',
    glimpse: '',
  },
  name: 'Kathryn',
  ic_birth_year: null,
  true_height_inches: null,
  weight_pounds: null,
  marital_status: 'single',
  vocation: '',
  social_rank: 10,
  build: null,
  gender: null,
  pronouns: null,
  species: null,
  heritage: null,
  origin_realm: null,
  family: null,
  tarot_card: null,
  tarot_reversed: false,
};

const ESTATE_OPTIONS = {
  open_positions: [{ id: 40, name: 'Second son (House Marrow)' }],
  families: [{ id: 41, name: 'House Marrow' }],
  rooms: [],
  grant_profiles: [],
  house_claims: [],
  vacancies: [],
  organizations: [{ id: 42, name: 'The Lamplighters' }],
};

const GROUP_OPTIONS = {
  characters: [],
  faces: [{ id: 70, name: 'Kathryn' }],
  relationship_types: [{ id: 50, name: 'Rival' }],
  awareness: [
    { value: 'private', label: 'Private' },
    { value: 'public', label: 'Public' },
  ],
  tiers: [{ id: 1, name: 'Acquainted' }],
  title_rewards: [],
  deeds: [],
  noble_titles: [],
  covenants: [
    {
      id: 60,
      name: 'The Lantern Oath',
      roles: [{ id: 61, name: 'Vanguard' }],
      ranks: [{ id: 62, name: 'Sworn' }],
    },
  ],
};

const OPTIONS = {
  stats: [
    { id: 1, name: 'strength' },
    { id: 2, name: 'wits' },
  ],
  skills: [],
  specializations: [],
  distinctions: [{ id: 30, name: 'Keen Eyes' }],
  form_traits: [],
  beginnings: [],
  paths: [],
  beings: [],
  marking_regions: [],
  marking_kinds: [],
  enemy_kinds: [],
  enemy_degrees: [],
  enemy_power_tiers: [],
};

function sheet(overrides: Partial<CharacterSheetPayload> = {}): CharacterSheetPayload {
  return {
    id: 20,
    can_edit: true,
    staff_edit: STORED,
    identity: {
      name: 'Kathryn',
      fullname: 'Kathryn',
      concept: '',
      quote: '',
      age: 24,
      birthday: null,
      gender: null,
      pronouns: { subject: 'she', object: 'her', possessive: 'her' },
      species: null,
      heritage: null,
      beginnings: [],
      family: null,
      tarot_card: null,
      origin: null,
      path: null,
      worship: null,
    },
    appearance: { height_inches: null, height_band: '', build: null, description: '' },
    stats: {},
    skills: [],
    distinctions: [],
    magic: null,
    story: { background: 'Raised at the quay.', origin_slots: [] },
    actor_sheet: { never_do: '', protect: '', fear: '', enemy_public_line: '', introductions: [] },
    goals: [],
    beats: [],
    ...overrides,
  } as unknown as CharacterSheetPayload;
}

function renderSheet(payload: CharacterSheetPayload) {
  return renderWithProviders(
    <StaffEditProvider sheet={payload}>
      <StaffEditToggle sheet={payload} />
      <SheetPanel sheet={payload} isMyCharacter={false} rumor={null} languages={null} />
    </StaffEditProvider>
  );
}

describe('staff edit mode', () => {
  beforeEach(() => {
    sessionStorage.clear();
    patchStaffEdit.mockReset();
    restoreProfileTextVersion.mockReset();
    fetchProfileTextVersions.mockReset();
    runStaffRowAction.mockReset();
    fetchStaffOptions.mockReset();
    fetchStaffOptions.mockResolvedValue(OPTIONS);
    fetchStaffMagicOptions.mockReset();
    fetchStaffEstateOptions.mockReset();
    fetchStaffEstateOptions.mockResolvedValue(ESTATE_OPTIONS);
    fetchStaffGroupOptions.mockReset();
    fetchStaffGroupOptions.mockImplementation((_sheetId: number, character: string) =>
      Promise.resolve({
        ...GROUP_OPTIONS,
        characters: character ? [{ id: 80, name: 'Ser Aldric' }] : [],
      })
    );
  });
  afterEach(() => sessionStorage.clear());

  it('draws no toggle for a payload without staff fields', () => {
    renderSheet(sheet({ staff_edit: null }));
    expect(screen.queryByRole('switch', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('staff-edit-band')).not.toBeInTheDocument();
  });

  it('is off until toggled; on, empty fields keep a slot', async () => {
    const user = userEvent.setup();
    renderSheet(sheet());
    expect(screen.queryByTestId('staff-edit-band')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit As they appear' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('switch', { name: 'Edit' }));

    expect(screen.getByTestId('staff-edit-band')).toBeInTheDocument();
    // The description is empty, so it is hidden off, and a slot on.
    expect(screen.getByRole('button', { name: 'Edit As they appear' })).toHaveTextContent('—');
    expect(sessionStorage.getItem('arx.staffEditMode')).toBe('1');
  });

  it('saves a prose field with Ctrl+Enter and cancels with Esc', async () => {
    const user = userEvent.setup();
    patchStaffEdit.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    await user.click(screen.getByRole('button', { name: 'Edit Where they come from' }));
    const box = screen.getByRole('textbox', { name: 'Where they come from' });
    expect(box).toHaveValue('Raised at the quay.');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('textbox', { name: 'Where they come from' })).not.toBeInTheDocument();
    expect(patchStaffEdit).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Edit Where they come from' }));
    const again = screen.getByRole('textbox', { name: 'Where they come from' });
    await user.clear(again);
    await user.type(again, 'Raised on the river.');
    fireEvent.keyDown(again, { key: 'Enter', ctrlKey: true });

    await waitFor(() =>
      expect(patchStaffEdit).toHaveBeenCalledWith(20, { background: 'Raised on the river.' })
    );
    await waitFor(() =>
      expect(
        screen.queryByRole('textbox', { name: 'Where they come from' })
      ).not.toBeInTheDocument()
    );
  });

  it('saves a number field as a number', async () => {
    const user = userEvent.setup();
    patchStaffEdit.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    await user.click(screen.getByRole('button', { name: 'Edit Social rank' }));
    const box = screen.getByRole('spinbutton', { name: 'Social rank' });
    await user.clear(box);
    await user.type(box, '4');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patchStaffEdit).toHaveBeenCalledWith(20, { social_rank: 4 }));
  });

  it("lists a field's versions and restores one", async () => {
    const user = userEvent.setup();
    fetchProfileTextVersions.mockResolvedValue([
      {
        id: 7,
        field: 'background',
        text: 'Raised at the old quay.',
        created_at: '2026-10-01T10:00:00Z',
        ic_date_display: '',
        era_display_name: 'Season 1',
        staff_edited: true,
        reasoning: '',
      },
      {
        id: 8,
        field: 'fear',
        text: 'Fire.',
        created_at: '2026-10-01T10:00:00Z',
        ic_date_display: '',
        era_display_name: null,
        staff_edited: false,
        reasoning: '',
      },
    ]);
    restoreProfileTextVersion.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    await user.click(screen.getByRole('button', { name: 'History of Where they come from' }));
    const history = await screen.findByRole('region', { name: 'Where they come from history' });
    expect(await within(history).findByText('Raised at the old quay.')).toBeInTheDocument();
    expect(within(history).queryByText('Fire.')).not.toBeInTheDocument();

    await user.click(within(history).getByRole('button', { name: 'Restore' }));
    await waitFor(() => expect(restoreProfileTextVersion).toHaveBeenCalledWith(20, 7));
  });

  it('saves the stats a staff editor fills on a sheet that had none (#4221)', async () => {
    const user = userEvent.setup();
    runStaffRowAction.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    const rowsBand = await screen.findByTestId('staff-rows-band');
    await user.type(within(rowsBand).getByRole('spinbutton', { name: 'strength' }), '3');
    await user.click(within(rowsBand).getByRole('button', { name: 'Save stats' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-stats',
        method: 'PATCH',
        body: { stats: { '1': 3 } },
      })
    );
  });

  it('removes a held distinction without a request (#4221)', async () => {
    const user = userEvent.setup();
    runStaffRowAction.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    const held = sheet({
      staff_edit: {
        ...STORED,
        rows: {
          ...STORED.rows,
          distinctions: [
            { id: 77, distinction: 30, name: 'Keen Eyes', rank: 1, max_rank: 1, feature: '' },
          ],
        },
      },
    });
    renderSheet(held);

    const rowsBand = await screen.findByTestId('staff-rows-band');
    await user.click(within(rowsBand).getByRole('button', { name: 'Remove Keen Eyes' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-distinction',
        method: 'PATCH',
        body: { character_distinction: 77 },
      })
    );
  });
  it('grants magic to a giftless sheet, each pick narrowing the next (#4224)', async () => {
    const user = userEvent.setup();
    runStaffRowAction.mockResolvedValue(sheet());
    fetchStaffMagicOptions.mockImplementation(
      async (_sheet: number, tradition: string, gift: string) => ({
        traditions: [{ id: 5, name: 'Lamplighters' }],
        gifts: tradition ? [{ id: 6, name: 'Embers' }] : [],
        techniques: gift
          ? [
              { id: 7, name: 'Kindle' },
              { id: 8, name: 'Smother' },
            ]
          : [],
        resonances: gift ? [{ id: 9, name: 'Warmth' }] : [],
        stats: [{ id: 1, name: 'strength' }],
        skills: [{ id: 2, name: 'Occult' }],
        technique_limit: 1,
      })
    );
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet({ staff_edit: { ...STORED, rows: { ...STORED.rows, has_gift: false } } }));

    const editor = await screen.findByTestId('staff-magic-editor');
    await user.selectOptions(within(editor).getByRole('combobox', { name: 'Tradition' }), '5');
    await user.selectOptions(await within(editor).findByRole('combobox', { name: 'Gift' }), '6');
    await user.click(await within(editor).findByRole('checkbox', { name: 'Kindle' }));
    expect(within(editor).getByRole('checkbox', { name: 'Smother' })).toBeDisabled();
    await user.selectOptions(within(editor).getByRole('combobox', { name: 'Resonance' }), '9');
    await user.selectOptions(within(editor).getByRole('combobox', { name: 'Anima stat' }), '1');
    await user.selectOptions(within(editor).getByRole('combobox', { name: 'Anima skill' }), '2');
    await user.type(within(editor).getByRole('textbox', { name: 'Glimpse' }), 'A spark.');
    await user.click(within(editor).getByRole('button', { name: 'Grant magic' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-magic',
        method: 'POST',
        body: {
          tradition: 5,
          gift: 6,
          techniques: [7],
          resonance: 9,
          anima_stat: 1,
          anima_skill: 2,
          ritual_name: '',
          glimpse: 'A spark.',
        },
      })
    );
  });

  it('offers no Grant magic once the sheet holds a gift (#4224)', async () => {
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());
    await screen.findByTestId('staff-rows-band');
    expect(screen.queryByTestId('staff-magic-editor')).not.toBeInTheDocument();
    expect(fetchStaffMagicOptions).not.toHaveBeenCalled();
  });
  it('claims an open kin position and sets a reputation (#4226)', async () => {
    const user = userEvent.setup();
    runStaffRowAction.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    const band = await screen.findByTestId('staff-rows-band');
    const tree = await within(band).findByRole('region', { name: 'Family tree' });
    await user.selectOptions(within(tree).getByRole('combobox', { name: 'Open position' }), '40');
    await user.click(within(tree).getByRole('button', { name: 'Claim position' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-kinship',
        method: 'POST',
        body: { node: 40 },
      })
    );

    const reputation = within(band).getByRole('region', { name: 'Reputation' });
    await user.selectOptions(
      within(reputation).getByRole('combobox', { name: 'Organization' }),
      '42'
    );
    await user.type(within(reputation).getByRole('spinbutton', { name: 'Reputation' }), '250');
    await user.click(within(reputation).getByRole('button', { name: 'Set reputation' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-reputation',
        method: 'PUT',
        body: { organization: 42, value: 250 },
      })
    );
  });

  it('shows the kin node in place of the pickers once the sheet has one (#4226)', async () => {
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(
      sheet({
        staff_edit: {
          ...STORED,
          rows: { ...STORED.rows, kin_node: { id: 9, name: 'Kathryn (House Marrow)' } },
        },
      })
    );
    const band = await screen.findByTestId('staff-rows-band');
    const tree = await within(band).findByRole('region', { name: 'Family tree' });
    expect(within(tree).getByText('Kathryn (House Marrow)')).toBeInTheDocument();
    expect(within(tree).queryByRole('button', { name: 'Claim position' })).not.toBeInTheDocument();
  });

  it('declares a label on a searched character and swears a covenant role (#4229)', async () => {
    const user = userEvent.setup();
    runStaffRowAction.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    const band = await screen.findByTestId('staff-rows-band');
    const ties = await within(band).findByRole('region', { name: 'Ties' });
    await user.type(within(ties).getByRole('textbox', { name: 'Find a character' }), 'Ald');
    await user.click(within(ties).getByRole('button', { name: 'Find' }));
    await waitFor(() => expect(fetchStaffGroupOptions).toHaveBeenLastCalledWith(20, 'Ald'));
    await user.selectOptions(
      await within(ties).findByRole('combobox', { name: 'Character' }),
      '80'
    );
    await user.selectOptions(within(ties).getByRole('combobox', { name: 'Side' }), 'from');
    await user.selectOptions(within(ties).getByRole('combobox', { name: 'Relationship' }), '50');
    await user.selectOptions(within(ties).getByRole('combobox', { name: 'Awareness' }), 'public');
    await user.click(within(ties).getByRole('button', { name: 'Declare' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-tie-labels',
        method: 'POST',
        body: { other: 80, direction: 'from', type: 50, awareness: 'public' },
      })
    );

    const covenants = within(band).getByRole('region', { name: 'Covenants' });
    await user.selectOptions(within(covenants).getByRole('combobox', { name: 'Covenant' }), '60');
    await user.selectOptions(within(covenants).getByRole('combobox', { name: 'Role' }), '61');
    await user.click(within(covenants).getByRole('button', { name: 'Swear in' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-covenant-roles',
        method: 'POST',
        body: { covenant: 60, covenant_role: 61, rank: null },
      })
    );
  });

  it('marks a waiting label and shows a bond outside the band with its warning (#4229)', async () => {
    const user = userEvent.setup();
    runStaffRowAction.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(
      sheet({
        staff_edit: {
          ...STORED,
          rows: {
            ...STORED.rows,
            ties: [
              {
                other: 80,
                other_name: 'Ser Aldric',
                toward: {
                  id: 5,
                  tier: 0,
                  summary: '',
                  labels: [{ id: 6, type: 50, name: 'Rival', awareness: 'private', waiting: true }],
                },
                back: null,
              },
            ],
            mentor_bonds: [
              {
                id: 7,
                covenant_name: 'The Lantern Oath',
                other_name: 'Ser Aldric',
                as_mentor: false,
                warning: 'Both parties are outside the covenant band.',
              },
            ],
          },
        },
      })
    );
    const band = await screen.findByTestId('staff-rows-band');
    const tie = await within(band).findByLabelText('Tie with Ser Aldric');
    expect(within(tie).getByText('(binds at pickup)')).toBeInTheDocument();
    await user.click(within(tie).getByRole('button', { name: 'End' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-tie-label',
        method: 'PATCH',
        body: { label: 6, end: true },
      })
    );
    const bonds = within(band).getByRole('region', { name: 'Mentor bonds' });
    expect(
      within(bonds).getByText('Both parties are outside the covenant band.')
    ).toBeInTheDocument();
  });
});

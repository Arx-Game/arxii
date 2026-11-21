import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { ApiError } from '@/lib/errors';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import * as api from '../api';
import { GameClockPage } from '../GameClockPage';
import type { ClockHistoryRow, ClockJumpPreview, ClockState } from '../types';

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  fetchClock: vi.fn(),
  fetchClockHistory: vi.fn(),
  fetchJumpPreview: vi.fn(),
  pauseClock: vi.fn(),
  resumeClock: vi.fn(),
  setClockDate: vi.fn(),
  setClockSpeed: vi.fn(),
}));

const MONTHS = [
  'Dreaming',
  'Choosing',
  'Thawing',
  'Waking',
  'Rising',
  'Vowing',
  'Enduring',
  'Gathering',
  'Unyielding',
  'Masquing',
  'Keeping',
  'Ending',
];

function makeClock(overrides: Partial<ClockState> = {}): ClockState {
  return {
    ic_datetime: '1000-03-09T16:20:00Z',
    year: 1000,
    month: 3,
    month_name: 'Thawing',
    date_display: 'the 9th of the Month of Thawing, Year 1000',
    day: 9,
    hour: 16,
    minute: 20,
    phase: 'day',
    season: 'spring',
    light_level: 1,
    paused: false,
    time_ratio: 3,
    month_names: MONTHS,
    ...overrides,
  };
}

function makePreview(overrides: Partial<ClockJumpPreview> = {}): ClockJumpPreview {
  return {
    current_ic_time: '1000-03-09T16:20:00Z',
    current_date_display: 'the 9th of the Month of Thawing, Year 1000',
    new_ic_time: '1020-03-09T16:20:00Z',
    direction: 'forward',
    year_shift: 20,
    characters_with_birth_year: 143,
    upcoming_events: 2,
    heritages_not_yet_appeared: [],
    ...overrides,
  };
}

function makeRow(overrides: Partial<ClockHistoryRow> = {}): ClockHistoryRow {
  return {
    id: 1,
    changed_at: '2026-11-21T22:14:00Z',
    changed_by_name: 'Apostate',
    change: 'paused',
    new_anchor_ic_time: '1000-01-01T00:00:00Z',
    new_date_display: 'the 1st of the Month of Dreaming, Year 1000',
    old_time_ratio: 3,
    new_time_ratio: 3,
    birth_year_shift: 0,
    reason: '',
    ...overrides,
  };
}

function history(results: ClockHistoryRow[]) {
  return { count: results.length, next: null, previous: null, results };
}

async function setYear(user: ReturnType<typeof userEvent.setup>, year: string) {
  const field = screen.getByLabelText('Year');
  await user.clear(field);
  await user.type(field, year);
}

describe('GameClockPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.fetchClockHistory).mockResolvedValue(history([]));
  });

  it('shows a running clock with its speed and offers Pause', async () => {
    vi.mocked(api.fetchClock).mockResolvedValue(makeClock());
    vi.mocked(api.pauseClock).mockResolvedValue();
    const user = userEvent.setup();

    renderWithProviders(<GameClockPage />);

    expect(await screen.findByText('the 9th of the Month of Thawing, Year 1000')).toBeVisible();
    expect(screen.getByText('Running')).toBeVisible();
    expect(screen.getByText('3 game days pass for each real day')).toBeVisible();
    expect(screen.getByText('16:20 · Spring · Day')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Resume from this date' })).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(api.pauseClock).toHaveBeenCalledTimes(1));
  });

  it('shows a paused clock and resumes it from the date shown', async () => {
    vi.mocked(api.fetchClock).mockResolvedValue(
      makeClock({ paused: true, date_display: 'the 1st of the Month of Dreaming, Year 1000' })
    );
    vi.mocked(api.resumeClock).mockResolvedValue();
    const user = userEvent.setup();

    renderWithProviders(<GameClockPage />);

    expect(await screen.findByText('Paused')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Resume from this date' }));
    await waitFor(() => expect(api.resumeClock).toHaveBeenCalledTimes(1));
  });

  it('says so in the server’s words when a control is refused', async () => {
    vi.mocked(api.fetchClock).mockResolvedValue(makeClock());
    vi.mocked(api.pauseClock).mockRejectedValue(
      new ApiError('Game clock is already paused.', { status: 400 })
    );
    const user = userEvent.setup();

    renderWithProviders(<GameClockPage />);
    await user.click(await screen.findByRole('button', { name: 'Pause' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Game clock is already paused.');
  });

  it('points at the admin when no clock exists', async () => {
    vi.mocked(api.fetchClock).mockRejectedValue(
      new ApiError('Game clock is not configured.', { status: 503 })
    );

    renderWithProviders(<GameClockPage />);

    const link = await screen.findByRole('link', { name: 'Create it in the admin' });
    expect(link).toHaveAttribute('href', '/admin/arxii/gameclock/add/');
    expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull();
  });

  it('lists the recent changes, each in a sentence', async () => {
    vi.mocked(api.fetchClock).mockResolvedValue(makeClock());
    vi.mocked(api.fetchClockHistory).mockResolvedValue(
      history([
        makeRow({
          id: 3,
          change: 'resumed',
          new_date_display: 'the 15th of the Month of Thawing, Year 1000',
        }),
        makeRow({
          id: 2,
          change: 'date_kept',
          birth_year_shift: 20,
          new_date_display: 'the 1st of the Month of Dreaming, Year 1020',
          reason: 'A new season',
        }),
        makeRow({ id: 1, change: 'speed', old_time_ratio: 3, new_time_ratio: 1 }),
      ])
    );

    renderWithProviders(<GameClockPage />);

    const table = await screen.findByRole('table');
    expect(
      within(table).getByText('Resumed at the 15th of the Month of Thawing, Year 1000')
    ).toBeVisible();
    expect(
      within(table).getByText(
        'Date set to the 1st of the Month of Dreaming, Year 1020. Characters kept their ages. Birth years moved by +20.'
      )
    ).toBeVisible();
    expect(
      within(table).getByText('Speed changed from 3 to 1 game days per real day')
    ).toBeVisible();
    expect(within(table).getByText('A new season')).toBeVisible();
    expect(within(table).getAllByText('Apostate')).toHaveLength(3);
  });

  describe('Set the date', () => {
    async function openDialog(clock: ClockState = makeClock()) {
      vi.mocked(api.fetchClock).mockResolvedValue(clock);
      const user = userEvent.setup();
      renderWithProviders(<GameClockPage />);
      await user.click(await screen.findByRole('button', { name: 'Set the date' }));
      return user;
    }

    it('offers the world’s month names and starts from the current date', async () => {
      await openDialog();

      const dialog = await screen.findByRole('dialog');
      expect(within(dialog).getByLabelText('Year')).toHaveValue(1000);
      expect(within(dialog).getByLabelText('Month')).toHaveValue('3');
      expect(within(dialog).getByRole('option', { name: 'Dreaming' })).toBeInTheDocument();
      expect(within(dialog).getAllByRole('option')).toHaveLength(12);
      // Nothing has changed yet, so there is nothing to confirm.
      expect(within(dialog).getByRole('button', { name: 'Set the date' })).toBeDisabled();
    });

    it('asks whether characters age on a forward jump, and names the jump on its button', async () => {
      vi.mocked(api.fetchJumpPreview).mockResolvedValue(makePreview());
      vi.mocked(api.setClockDate).mockResolvedValue();
      const user = await openDialog();

      await setYear(user, '1020');

      const submit = await screen.findByRole('button', { name: 'Move the world 20 years forward' });
      expect(screen.getByText(/This moves the world/)).toHaveTextContent(
        'This moves the world 20 years forward, from the 9th of the Month of Thawing, Year 1000.'
      );
      const aged = screen.getByRole('radio', { name: /Characters age/ });
      const kept = screen.getByRole('radio', { name: /Characters keep their ages/ });
      expect(aged).not.toBeChecked();
      expect(kept).not.toBeChecked();
      expect(screen.getByText(/Each of the 143 characters/)).toHaveTextContent(
        'becomes 20 years older'
      );
      expect(screen.getByText(/Every birth year moves forward by 20/)).toBeVisible();
      expect(screen.getByText('2 upcoming events move with it.')).toBeVisible();
      expect(screen.getByText('The clock keeps running from the new date.')).toBeVisible();

      // Neither a choice alone nor a reason alone is enough.
      expect(submit).toBeDisabled();
      await user.click(kept);
      expect(submit).toBeDisabled();
      await user.type(screen.getByLabelText('Reason'), 'A new season');
      expect(submit).toBeEnabled();

      await user.click(submit);
      await waitFor(() =>
        expect(api.setClockDate).toHaveBeenCalledWith({
          ic_datetime: '1020-03-09T16:20:00Z',
          reason: 'A new season',
          age_handling: 'kept',
        })
      );
      await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
      expect(api.fetchJumpPreview).toHaveBeenLastCalledWith('1020-03-09T16:20:00Z');
    });

    it('offers no choice on a change to an earlier date, and warns of a heritage not yet appeared', async () => {
      vi.mocked(api.fetchJumpPreview).mockResolvedValue(
        makePreview({
          direction: 'back',
          year_shift: -50,
          upcoming_events: 0,
          heritages_not_yet_appeared: ['Misbegotten'],
        })
      );
      vi.mocked(api.setClockDate).mockResolvedValue();
      const user = await openDialog(makeClock({ paused: true }));

      await setYear(user, '950');

      const submit = await screen.findByRole('button', { name: 'Move the world 50 years back' });
      expect(screen.queryByRole('radio')).toBeNull();
      expect(screen.getByText(/Characters keep their ages\./)).toBeVisible();
      expect(screen.getByText(/Every birth year moves back by 50/)).toBeVisible();
      expect(screen.getByText('The clock is paused and stays paused.')).toBeVisible();
      expect(screen.getByText(/Misbegotten first appeared after this date/)).toBeVisible();
      expect(screen.queryByText(/upcoming event/)).toBeNull();

      await user.type(screen.getByLabelText('Reason'), 'A season in the old kingdom');
      await user.click(submit);
      await waitFor(() =>
        expect(api.setClockDate).toHaveBeenCalledWith({
          ic_datetime: '0950-03-09T16:20:00Z',
          reason: 'A season in the old kingdom',
          age_handling: 'kept',
        })
      );
    });

    it('refuses a date that does not exist without asking the server', async () => {
      const user = await openDialog();

      const day = screen.getByLabelText('Day');
      await user.clear(day);
      await user.type(day, '31');
      await user.selectOptions(screen.getByLabelText('Month'), 'Choosing');

      expect(await screen.findByText('That date does not exist.')).toBeVisible();
      expect(screen.getByRole('button', { name: 'Set the date' })).toBeDisabled();
      expect(api.fetchJumpPreview).not.toHaveBeenCalledWith('1000-02-31T16:20:00Z');
    });

    it('keeps the dialog open and says why when the server refuses', async () => {
      vi.mocked(api.fetchJumpPreview).mockResolvedValue(makePreview());
      vi.mocked(api.setClockDate).mockRejectedValue(
        new ApiError("A change to an earlier date keeps characters' ages.", { status: 400 })
      );
      const user = await openDialog();

      await setYear(user, '1020');
      await user.click(await screen.findByRole('radio', { name: /Characters age/ }));
      await user.type(screen.getByLabelText('Reason'), 'x');
      await user.click(screen.getByRole('button', { name: 'Move the world 20 years forward' }));

      expect(await screen.findByRole('alert')).toHaveTextContent(
        "A change to an earlier date keeps characters' ages."
      );
      expect(screen.getByRole('dialog')).toBeVisible();
    });
  });

  it('changes the speed with a number and a reason', async () => {
    vi.mocked(api.fetchClock).mockResolvedValue(makeClock());
    vi.mocked(api.setClockSpeed).mockResolvedValue();
    const user = userEvent.setup();

    renderWithProviders(<GameClockPage />);
    await user.click(await screen.findByRole('button', { name: 'Change speed' }));

    const dialog = await screen.findByRole('dialog');
    const ratio = within(dialog).getByLabelText('Game days per real day');
    expect(ratio).toHaveValue(3);
    const submit = within(dialog).getByRole('button', { name: 'Change speed' });
    expect(submit).toBeDisabled();
    await user.clear(ratio);
    await user.type(ratio, '1');
    await user.type(within(dialog).getByLabelText('Reason'), 'A slow weekend');
    await user.click(submit);

    await waitFor(() =>
      expect(api.setClockSpeed).toHaveBeenCalledWith({ ratio: 1, reason: 'A slow weekend' })
    );
  });
});

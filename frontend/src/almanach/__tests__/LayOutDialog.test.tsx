/**
 * LayOutDialog (#4983 slice 2, #4986): a textarea for the layout, Preview renders the
 * report, Lay out dispatches the text, and the last text is remembered per realm.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { LayOutDialog, type LayoutReport } from '../ladder/LayOutDialog';

const REPORT: LayoutReport = {
  wrote: false,
  refusals: ['line 3: no kingdom named Nowhere on the ladder'],
  kingdoms: [
    {
      name: 'Luxen',
      line_no: 2,
      planted: { duchy: 2, county: 5, barony: 11 },
      duchies: [
        { name: 'Ashford', pips: 60, capital: true },
        { name: 'Brackwater', pips: 30, capital: false },
        { name: 'Coldharbour', pips: 30, capital: false },
      ],
      names: ['Ashford', 'Brackwater', 'Coldharbour'],
      charters: [],
      claims: ['Sharlotte claims Luxen'],
      refusals: [],
    },
    {
      name: 'Nowhere',
      line_no: 3,
      planted: {},
      duchies: [],
      names: [],
      charters: [],
      claims: [],
      refusals: ['line 3: no kingdom named Nowhere on the ladder'],
    },
  ],
};

const LAYOUT = 'realm | counties 2\nkingdom Luxen | duchies 3\nkingdom Nowhere\n';

beforeEach(() => {
  window.localStorage.clear();
});

test('Preview sends the text and renders the report per kingdom', async () => {
  const onPreview = vi.fn().mockResolvedValue(REPORT);
  renderWithProviders(
    <LayOutDialog
      open
      realmId={1}
      realmName="Luxen"
      onClose={() => {}}
      onPreview={onPreview}
      onLayOut={vi.fn()}
    />
  );
  await userEvent.type(screen.getByLabelText('layout'), LAYOUT);
  await userEvent.click(screen.getByRole('button', { name: 'Preview' }));
  expect(onPreview).toHaveBeenCalledWith(LAYOUT);
  const luxen = await screen.findByTestId('layout-kingdom-Luxen');
  expect(within(luxen).getByText('Ashford')).toBeInTheDocument();
  expect(within(luxen).getByText('60')).toBeInTheDocument();
  expect(within(luxen).getByText('Sharlotte claims Luxen')).toBeInTheDocument();
  const nowhere = screen.getByTestId('layout-kingdom-Nowhere');
  expect(within(nowhere).getByText('line 3: no kingdom named Nowhere on the ladder')).toBeVisible();
});

test('Lay out sends the text and remembers it for the realm', async () => {
  const onLayOut = vi.fn().mockResolvedValue({ ...REPORT, wrote: true, refusals: [] });
  const onClose = vi.fn();
  renderWithProviders(
    <LayOutDialog
      open
      realmId={1}
      realmName="Luxen"
      onClose={onClose}
      onPreview={vi.fn()}
      onLayOut={onLayOut}
    />
  );
  await userEvent.type(screen.getByLabelText('layout'), 'kingdom Luxen | duchies 3');
  await userEvent.click(screen.getByRole('button', { name: 'Lay out' }));
  expect(onLayOut).toHaveBeenCalledWith('kingdom Luxen | duchies 3');
  expect(window.localStorage.getItem('almanach:layout:1')).toBe('kingdom Luxen | duchies 3');
  expect(onClose).toHaveBeenCalled();
});

test('a remembered layout fills the textarea when the dialog opens', () => {
  window.localStorage.setItem('almanach:layout:1', 'kingdom Umbros | duchies 5');
  renderWithProviders(
    <LayOutDialog
      open
      realmId={1}
      realmName="Luxen"
      onClose={() => {}}
      onPreview={vi.fn()}
      onLayOut={vi.fn()}
    />
  );
  expect(screen.getByLabelText('layout')).toHaveValue('kingdom Umbros | duchies 5');
  expect(screen.getByRole('button', { name: 'Lay out' })).toBeEnabled();
});

test('Lay out keeps the dialog open and shows the refusals when a kingdom is refused', async () => {
  const refused = {
    ...REPORT,
    wrote: true,
    refusals: ['line 2: Luxen already has rungs beneath it'],
    kingdoms: [{ ...REPORT.kingdoms[0], refusals: ['line 2: Luxen already has rungs beneath it'] }],
  };
  const onClose = vi.fn();
  renderWithProviders(
    <LayOutDialog
      open
      realmId={1}
      realmName="Luxen"
      onClose={onClose}
      onPreview={vi.fn()}
      onLayOut={vi.fn().mockResolvedValue(refused)}
    />
  );
  await userEvent.type(screen.getByLabelText('layout'), 'kingdom Luxen | duchies 3');
  await userEvent.click(screen.getByRole('button', { name: 'Lay out' }));
  expect(await screen.findByText('line 2: Luxen already has rungs beneath it')).toBeInTheDocument();
  expect(onClose).not.toHaveBeenCalled();
});

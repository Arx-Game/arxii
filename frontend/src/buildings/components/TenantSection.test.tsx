import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { ManagerRoom } from '../types';
import { TenantSection } from './TenantSection';

vi.mock('../queries', () => ({
  usePersonaSearchQuery: vi.fn(),
}));

const { usePersonaSearchQuery } = await import('../queries');

/**
 * #3902 — the tenant section is the one player surface that mints a grant, so it
 * has to be able to say WHICH rung. Before the ladder every grant it made was a
 * tenancy; now a key and a trusteeship are the same click with a different rung.
 */
function roomWith(tenancies: ManagerRoom['tenancies']): ManagerRoom {
  return { id: 7, name: 'The Blue Parlour', tenancies } as unknown as ManagerRoom;
}

function renderSection(tenancies: ManagerRoom['tenancies'] = []) {
  const runAction = vi.fn();
  vi.mocked(usePersonaSearchQuery).mockReturnValue({
    data: [{ id: 42, name: 'Isolde' }],
    isLoading: false,
  } as never);
  renderWithProviders(<TenantSection room={roomWith(tenancies)} runAction={runAction} />);
  return { runAction };
}

describe('TenantSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows each grant with its rung, so a key does not read as someone who lives here', () => {
    renderSection([
      {
        id: 1,
        tenant_persona_id: 10,
        tenant_name: 'Maelis',
        kind: 'guest',
        is_primary_home: false,
        ends_at: null,
      },
      {
        id: 2,
        tenant_persona_id: 11,
        tenant_name: 'Corvin',
        kind: 'tenant',
        is_primary_home: true,
        ends_at: null,
      },
      {
        id: 3,
        tenant_persona_id: 12,
        tenant_name: 'Sable',
        kind: 'trustee',
        is_primary_home: false,
        ends_at: null,
      },
    ]);
    const section = within(screen.getByTestId('tenant-section'));
    expect(section.getByText('Maelis').parentElement).toHaveTextContent('key');
    expect(section.getByText('Corvin').parentElement).toHaveTextContent('tenant');
    expect(section.getByText('Corvin').parentElement).toHaveTextContent('home');
    expect(section.getByText('Sable').parentElement).toHaveTextContent('trustee');
  });

  it('grants a tenancy by default', async () => {
    const { runAction } = renderSection();
    await userEvent.type(screen.getByTestId('tenant-search'), 'Is');
    await userEvent.click(screen.getByRole('button', { name: 'Isolde' }));
    expect(runAction).toHaveBeenCalledWith('assign_room_tenant', {
      room_id: 7,
      tenant_persona_id: 42,
      kind: 'tenant',
    });
  });

  it('hands out a key when Key is the chosen rung', async () => {
    const { runAction } = renderSection();
    await userEvent.click(screen.getByRole('radio', { name: 'Key' }));
    expect(screen.getByTestId('tenant-search')).toHaveAttribute(
      'placeholder',
      expect.stringContaining('Give a key to')
    );
    await userEvent.type(screen.getByTestId('tenant-search'), 'Is');
    await userEvent.click(screen.getByRole('button', { name: 'Isolde' }));
    expect(runAction).toHaveBeenCalledWith('assign_room_tenant', {
      room_id: 7,
      tenant_persona_id: 42,
      kind: 'guest',
    });
  });

  it('appoints a trustee when Trustee is the chosen rung', async () => {
    const { runAction } = renderSection();
    await userEvent.click(screen.getByRole('radio', { name: 'Trustee' }));
    await userEvent.type(screen.getByTestId('tenant-search'), 'Is');
    await userEvent.click(screen.getByRole('button', { name: 'Isolde' }));
    expect(runAction).toHaveBeenCalledWith(
      'assign_room_tenant',
      expect.objectContaining({ kind: 'trustee' })
    );
  });

  it('takes a key back through the same end action as a tenancy', async () => {
    const { runAction } = renderSection([
      {
        id: 1,
        tenant_persona_id: 10,
        tenant_name: 'Maelis',
        kind: 'guest',
        is_primary_home: false,
        ends_at: null,
      },
    ]);
    await userEvent.click(screen.getByRole('button', { name: 'End' }));
    expect(screen.getByText("Take back Maelis's key?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Take back the key' }));
    expect(runAction).toHaveBeenCalledWith('end_room_tenancy', { tenancy_id: 1 });
  });
});

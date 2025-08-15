import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { EntityContextMenu } from './EntityContextMenu';

const sendMock = vi.fn();

vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({ send: sendMock }),
}));

describe('EntityContextMenu', () => {
  it('renders icons and sends commands', async () => {
    render(
      <EntityContextMenu
        character="Tester"
        commands={[
          {
            action: 'look',
            prompt: 'look target',
            params_schema: { target: { type: 'string' } },
            icon: '',
          },
        ]}
      />
    );

    const input = screen.getByLabelText(/look target/i);
    await userEvent.type(input, 'rock');
    const button = screen.getByRole('button', { name: /look/i });
    await userEvent.click(button);
    expect(sendMock).toHaveBeenCalledWith('Tester', 'look rock');
  });
});

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SoulfrayAcceptGate } from './SoulfrayAcceptGate';

const warning = {
  stage_name: 'Fractured',
  stage_description: 'Your soul strains.',
  has_death_risk: false,
};

describe('SoulfrayAcceptGate', () => {
  it('renders the warning prose and stage name', () => {
    render(
      <SoulfrayAcceptGate
        warning={warning}
        techniqueName="Firebolt"
        animaCost={3}
        accepted={false}
        onAcceptChange={() => {}}
      />
    );
    expect(screen.getByText(/Fractured/)).toBeInTheDocument();
    expect(screen.getByText(/Firebolt/)).toBeInTheDocument();
  });

  it('disables submit intent until accepted', () => {
    const onChange = vi.fn();
    render(
      <SoulfrayAcceptGate
        warning={warning}
        techniqueName="Firebolt"
        animaCost={3}
        accepted={false}
        onAcceptChange={onChange}
      />
    );
    const checkbox = screen.getByRole('checkbox', { name: /accept the risk/i });
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('uses red styling when has_death_risk', () => {
    render(
      <SoulfrayAcceptGate
        warning={{ ...warning, has_death_risk: true }}
        techniqueName="Firebolt"
        animaCost={3}
        accepted={false}
        onAcceptChange={() => {}}
      />
    );
    const gate = screen.getByTestId('soulfray-accept-gate');
    expect(gate.className).toContain('red');
  });
});

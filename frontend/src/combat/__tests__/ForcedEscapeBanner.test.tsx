import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ForcedEscapeBanner } from '../components/ForcedEscapeBanner';

describe('ForcedEscapeBanner', () => {
  it('renders the "you must run" call to flee', () => {
    render(<ForcedEscapeBanner />);
    expect(screen.getByRole('alert')).toHaveTextContent(/run/i);
  });
});

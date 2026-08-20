import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PerspectivesPanel } from '@/character-creation/components/PerspectivesPanel';

const perspectives = [
  {
    entry_id: 1,
    name: 'Duskborn Doorways',
    summary: 'They talk to doors.',
    lore_content: 'Every Duskborn home has a second door no guest may use.',
    subject_name: 'The Duskborn',
  },
  {
    entry_id: 2,
    name: 'Choir Silences',
    summary: 'Their silences are contracts.',
    lore_content: 'A Choir pause mid-sentence binds harder than any oath.',
    subject_name: 'The Silent Choir',
  },
];

describe('PerspectivesPanel', () => {
  it('renders one section per opinion with subject heading and full lore text', () => {
    render(<PerspectivesPanel perspectives={perspectives} />);
    expect(screen.getByText('On The Duskborn')).toBeInTheDocument();
    expect(screen.getByText('On The Silent Choir')).toBeInTheDocument();
    expect(
      screen.getByText('Every Duskborn home has a second door no guest may use.')
    ).toBeInTheDocument();
  });

  it('renders nothing when there are no perspectives', () => {
    const { container } = render(<PerspectivesPanel perspectives={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing while data is undefined', () => {
    const { container } = render(<PerspectivesPanel perspectives={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});

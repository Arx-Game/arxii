/**
 * The label catalogue's five families, in the order every surface draws them (#3957).
 *
 * Its own module rather than a constant beside one of the components, because both the
 * picker and the shift select group by it and neither is the other's owner.
 */
import type { RelationshipType } from '../api';

export const FAMILIES: Array<{ key: RelationshipType['family']; heading: string }> = [
  { key: 'heart', heading: 'Heart' },
  { key: 'company', heading: 'Company' },
  { key: 'contest', heading: 'Contest' },
  { key: 'blood_and_oath', heading: 'Blood and oath' },
  { key: 'teaching', heading: 'Teaching' },
];

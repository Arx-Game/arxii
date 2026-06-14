import type { components } from '@/generated/api';

/**
 * Fashion presentation + peer-judging types (#514, Outfits Phase C).
 *
 * The read shape (``FashionPresentation``) carries ``presenter`` as a
 * CharacterSheet pk only — there is no presenter name in the payload. The
 * panel resolves the viewer's own pk from the active roster entry to mark
 * "(You)" and to hide the Judge action on the viewer's own row.
 */
export type FashionPresentation = components['schemas']['FashionPresentation'];
export type PresentationPayload = components['schemas']['FashionPresentationRequest'];
export type JudgementPayload = components['schemas']['FashionJudgementRequest'];

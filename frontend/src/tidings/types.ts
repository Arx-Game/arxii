/** Public-reaction tidings feed API types (#1450), from the generated OpenAPI schema. */
import type { components } from '@/generated/api';

/** One row of the public feed: a deed your societies celebrate or a scandal they whisper about. */
export type PublicFeedItem = components['schemas']['PublicFeedItem'];
export type FeedItemKind = components['schemas']['PublicFeedItemKindEnum'];

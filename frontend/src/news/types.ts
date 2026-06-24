/** Public-reaction news feed API types (#1450).
 *
 * Hand-written (not from the generated OpenAPI schema) to keep this slice's diff contained to the
 * news feature. The shape matches `world.news.serializers.PublicFeedItemSerializer`. */

export type FeedItemKind = 'deed' | 'scandal';

/** One row of the public feed: a deed your societies celebrate or a scandal they whisper about. */
export interface PublicFeedItem {
  kind: FeedItemKind;
  headline: string;
  subject: string;
  occurred_at: string;
}

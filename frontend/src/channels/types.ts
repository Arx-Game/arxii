/**
 * Player channels (#3299): aliases over the generated OpenAPI schema for
 * `/api/channels/`. No type here carries an account or an author tenure id.
 */
import type { components } from '@/generated/api';

export type Channel = components['schemas']['Channel'];
export type ChannelSubscription = components['schemas']['ChannelSubscription'];
export type ChannelIdentity = components['schemas']['ChannelIdentity'];
export type ChannelMessage = components['schemas']['ChannelMessage'];
export type ChannelMessagePage = components['schemas']['PaginatedChannelMessageList'];
export type ChannelNotificationLevel = components['schemas']['ChannelNotificationLevelEnum'];
export type ChannelSubscriptionPatch = components['schemas']['PatchedChannelSubscriptionRequest'];

/** A joined channel: the channel row with its (non-null) subscription. */
export type JoinedChannel = Channel & { subscription: ChannelSubscription };

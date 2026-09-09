export type ConversationKind = 'room' | 'place' | 'whisper' | 'scene_ooc' | 'channel';
export type Availability = 'retained' | 'temporary' | 'unavailable';

export interface PoseRef {
  id: string;
  timestamp: string;
}
export interface ConversationRef {
  kind: ConversationKind;
  key: string;
}
export interface ConversationSummary {
  ref: ConversationRef;
  title: string;
  availability: Availability;
  canRead: boolean;
  canSend: boolean;
  sceneId: string | null;
  latestVisiblePose: PoseRef | null;
  unread: number;
  directUnread: number;
}
export interface ThreadSummary {
  id: string;
  conversation: ConversationRef;
  root: PoseRef | null;
  firstVisible: PoseRef;
  latestVisible: PoseRef;
  opening: string;
  visiblePoseCount: number;
  unread: number;
  directUnread: number;
}
export interface PlayPage<T> {
  results: T[];
  before: string | null;
  after: string | null;
  snapshot: string;
}
export interface PlaySearchResult {
  pose: PoseRef;
  conversation: ConversationRef;
  title: string;
  excerpt: string;
  availability: Availability;
}

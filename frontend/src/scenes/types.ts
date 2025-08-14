export interface RosterEntryRef {
  id: number;
  name: string;
  profile_url?: string;
}

export interface SceneParticipant {
  id: number;
  name: string;
  roster_entry?: RosterEntryRef | null;
}

export interface SceneParticipantRef extends SceneParticipant {
  roster_entry: RosterEntryRef;
}

export interface SceneSummary {
  id: number;
  name: string;
  participants: SceneParticipantRef[];
}

export interface SceneLocation {
  id: number;
  name: string;
}

export interface SceneListItem {
  id: number;
  name: string;
  description: string;
  date_started: string;
  location?: SceneLocation | null;
  participants: SceneParticipant[];
}

export interface SceneMessage {
  id: number;
  persona: { id: number; name: string; thumbnail_url?: string };
  content: string;
  timestamp: string;
  reactions: { emoji: string; count: number; reacted: boolean }[];
}

export interface SceneDetail extends SceneListItem {
  highlight_message: SceneMessage | null;
  is_active: boolean;
  is_owner: boolean;
}

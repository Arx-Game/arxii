/**
 * IC missives (#3289): read shapes from `GET /api/missives/` (see
 * `src/world/messengers/serializers.py`). Hand-authored, like `@/trade/api.ts`,
 * to avoid regenerating the shared OpenAPI schema on this branch.
 */

export type MissiveDirection = 'received' | 'sent';

export type AttachmentResolution = 'pending' | 'accepted' | 'refused';

export interface MissiveAttachment {
  id: number;
  kind: 'item' | 'coin';
  label: string;
  resolution: AttachmentResolution;
}

export interface Missive {
  id: number;
  direction: MissiveDirection;
  /** The other side, as the reader knows them. */
  counterpart_name: string;
  /** The reader's own face on this letter (sender for sent, recipient for received). */
  own_persona_id: number;
  own_persona_name: string;
  method_name: string;
  body: string;
  ic_date: string;
  sent_at: string;
  is_read: boolean;
  in_reply_to: number | null;
  attachments: MissiveAttachment[];
}

/** A face a missive can be addressed to (`GET /api/missives/addressees/`). */
export interface MissiveAddressee {
  id: number;
  name: string;
}

export type MissiveActionKey =
  'send_missive' | 'reply_missive' | 'read_missive' | 'accept_missive' | 'refuse_missive';

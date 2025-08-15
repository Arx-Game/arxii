export interface PlayerMail {
  id: number;
  recipient_tenure: number;
  recipient_display: string;
  subject: string;
  message: string;
  in_reply_to: number | null;
  sent_date: string;
  read_date: string | null;
  sender_tenure: number | null;
  sender_display: string;
}

export interface MailFormData {
  recipient_tenure: number;
  sender_tenure: number;
  subject: string;
  message: string;
  in_reply_to?: number;
}

export interface RosterTenureOption {
  id: number;
  display_name: string;
}

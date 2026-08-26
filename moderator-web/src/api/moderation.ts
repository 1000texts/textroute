import { apiRequest } from "./client";

export type MemberBrief = {
  id: string;
  name: string | null;
  phone_number: string;
  role?: string;
  suggested?: boolean;
  reason?: string;
};

export type ModerationMessage = {
  id: string;
  group_id: string;
  body: string;
  workflow_status: string;
  intent: string | null;
  confidence: number | null;
  constraints: Record<string, unknown> | null;
  sender: MemberBrief | null;
  suggested_recipients: MemberBrief[];
  approved_recipients: MemberBrief[];
  eligible_recipients?: MemberBrief[];
  processing_notes: string | null;
  created_at: string | null;
  delivered_outbound_ids?: string[];
  delivery_failures?: { member_id: string; error: string }[];
};

export function fetchModerationQueue(): Promise<ModerationMessage[]> {
  return apiRequest("/moderation/queue");
}

export function fetchMessage(messageId: string): Promise<ModerationMessage> {
  return apiRequest(`/messages/${messageId}`);
}

export function approveMessage(
  messageId: string,
  recipientIds: string[],
): Promise<ModerationMessage> {
  return apiRequest(`/messages/${messageId}/approve`, {
    method: "POST",
    body: JSON.stringify({ recipient_ids: recipientIds }),
  });
}

export function rejectMessage(messageId: string): Promise<ModerationMessage> {
  return apiRequest(`/messages/${messageId}/reject`, {
    method: "POST",
  });
}

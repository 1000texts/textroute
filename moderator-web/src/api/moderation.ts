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
  // Who the message was routed to — a moderator approved, or a group policy
  // authorized. Read workflow_status to tell which.
  routed_recipients: MemberBrief[];
  eligible_recipients?: MemberBrief[];
  kind: string | null;
  routing_policy: string | null;
  processing_notes: string | null;
  created_at: string | null;
  delivered_outbound_ids?: string[];
  delivery_failures?: { member_id: string; error: string }[];
};

/** Source of truth for the "needs review" count. */
export function fetchModerationQueue(): Promise<ModerationMessage[]> {
  return apiRequest("/moderation/queue");
}

/** Every inbound message, whatever its state. Capped server-side at 100. */
export function listMessages(): Promise<ModerationMessage[]> {
  return apiRequest("/messages");
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

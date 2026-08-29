import { apiRequest } from "./client";
import type { MemberBrief } from "./moderation";

/** One message inside a request thread. */
export type ThreadMessage = {
  id: string;
  direction: string;
  sender_role: string | null;
  kind: string | null;
  body: string;
  workflow_status: string;
  /**
   * The message this one hangs off. For a fan-out copy it is the authorized
   * message being fanned out, which makes it the identity of that routing
   * operation and the key the routing block groups by.
   */
  parent_message_id: string | null;
  /** Who the message is about: the sender inbound, the recipient outbound. */
  member: MemberBrief | null;
  /** Who wrote it. Null for a fan-out copy, which nobody wrote. */
  author: MemberBrief | null;
  created_at: string | null;
};

export type RequestEvent = {
  id: number;
  event_type: string;
  message_id: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
};

export type RequestSummary = {
  id: number;
  group_id: string;
  status: string;
  request_type: string | null;
  summary: string | null;
  /** How sure the analyzer was. Null means it never ran, which is not zero. */
  confidence: number | null;
  extracted_filters: Record<string, unknown> | null;
  has_embedding: boolean;
  model_name: string | null;
  requester: MemberBrief | null;
  original_message_id: string | null;
  created_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  expires_at: string | null;
  /**
   * Members party to the request: the requester, whoever fan-out reached, and
   * anyone who answered. A moderator acts on a request without being in it.
   */
  participant_count: number;
  message_count: number;
  last_activity_at: string | null;
  /**
   * A message here is waiting on a human. Not a status: a request can be open
   * with or without this, which is why the UI keeps the two axes apart.
   */
  needs_review: boolean;
};

export type RequestDetail = RequestSummary & {
  messages: ThreadMessage[];
  events: RequestEvent[];
};

export function listRequests(status?: string): Promise<RequestSummary[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest(`/requests${query}`);
}

export function fetchRequest(requestId: number): Promise<RequestDetail> {
  return apiRequest(`/requests/${requestId}`);
}

/**
 * Send the moderator's own words into the thread.
 *
 * Omitting recipients sends to the requester alone, which is what a clarifying
 * question usually wants.
 */
export function sendRequestMessage(
  requestId: number,
  body: string,
  recipientIds?: string[],
): Promise<{
  sent_message_ids: string[];
  failures: { member_id: string; error: string }[];
}> {
  return apiRequest(`/requests/${requestId}/messages`, {
    method: "POST",
    body: JSON.stringify({ body, recipient_ids: recipientIds ?? null }),
  });
}

export function completeRequest(requestId: number): Promise<RequestSummary> {
  return apiRequest(`/requests/${requestId}/complete`, { method: "POST" });
}

export function cancelRequest(requestId: number): Promise<RequestSummary> {
  return apiRequest(`/requests/${requestId}/cancel`, { method: "POST" });
}

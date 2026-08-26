export type CreateGroupPayload = {
  name: string;
  description: string | null;
  moderator_phone_number: string;
};

export type GroupResponse = {
  id: string;
  name: string;
  description: string | null;
  status: string;
  moderator_member_id: string;
  phone_number?: string;
};

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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:6060";

async function readError(res: Response): Promise<string> {
  const detail = await res.text();
  return detail || `Request failed (${res.status})`;
}

export async function createGroup(
  payload: CreateGroupPayload,
): Promise<GroupResponse> {
  const res = await fetch(`${API_BASE_URL}/groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await readError(res));
  }

  return res.json();
}

export async function fetchModerationQueue(
  groupId: string,
): Promise<ModerationMessage[]> {
  const res = await fetch(`${API_BASE_URL}/groups/${groupId}/moderation/queue`);
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return res.json();
}

export async function fetchMessage(messageId: string): Promise<ModerationMessage> {
  const res = await fetch(`${API_BASE_URL}/messages/${messageId}`);
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return res.json();
}

export async function approveMessage(
  messageId: string,
  recipientIds: string[],
): Promise<ModerationMessage> {
  const res = await fetch(`${API_BASE_URL}/messages/${messageId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recipient_ids: recipientIds }),
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return res.json();
}

export async function rejectMessage(messageId: string): Promise<ModerationMessage> {
  const res = await fetch(`${API_BASE_URL}/messages/${messageId}/reject`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return res.json();
}

export async function addGroupMember(
  groupId: string,
  payload: { phone_number: string; name?: string },
): Promise<unknown> {
  const res = await fetch(`${API_BASE_URL}/groups/${groupId}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(await readError(res));
  }
  return res.json();
}

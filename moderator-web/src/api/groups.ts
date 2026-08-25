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
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:6060";

export async function createGroup(
  payload: CreateGroupPayload,
): Promise<GroupResponse> {
  const res = await fetch(`${API_BASE_URL}/groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed (${res.status})`);
  }

  return res.json();
}

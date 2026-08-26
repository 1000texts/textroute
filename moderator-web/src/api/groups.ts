import { apiRequest } from "./client";

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
  phone_number: string;
};

export function createGroup(
  payload: CreateGroupPayload,
): Promise<GroupResponse> {
  return apiRequest("/groups", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

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

export type GroupSettings = {
  id: string;
  name: string;
  description: string | null;
  status: string;
  routing_policy: string;
};

export function createGroup(
  payload: CreateGroupPayload,
): Promise<GroupResponse> {
  return apiRequest("/groups", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getGroupSettings(): Promise<GroupSettings> {
  return apiRequest("/group/settings");
}

export function updateRoutingPolicy(
  routingPolicy: string,
): Promise<GroupSettings> {
  return apiRequest("/group/settings", {
    method: "PATCH",
    body: JSON.stringify({ routing_policy: routingPolicy }),
  });
}

import { apiRequest } from "./client";

export type ModeratorSession = {
  group_id: string;
  moderator_member_id: string;
  group_name: string;
  group_phone_number: string;
  expires_at: string;
};

export type ChallengeResponse = {
  challenge_id: string;
  expires_at: string;
  development_code: string | null;
};

export function requestModeratorChallenge(payload: {
  group_phone_number: string;
  moderator_phone_number: string;
}): Promise<ChallengeResponse> {
  return apiRequest("/auth/challenge", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function verifyModeratorChallenge(payload: {
  challenge_id: string;
  code: string;
}): Promise<ModeratorSession> {
  return apiRequest("/auth/verify", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getModeratorSession(): Promise<ModeratorSession> {
  return apiRequest("/auth/session");
}

export function logoutModerator(): Promise<void> {
  return apiRequest("/auth/logout", { method: "POST" });
}

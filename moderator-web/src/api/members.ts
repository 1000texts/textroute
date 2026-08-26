import { apiRequest } from "./client";

export type MemberInput = {
  phone_number: string;
  name: string;
};

export type AddedMember = MemberInput & {
  member_id: string;
  membership_id: string;
};

export type AddMembersResponse = {
  group_id: string;
  members: AddedMember[];
};

export function addMembers(
  members: MemberInput[],
  consentConfirmed: boolean,
): Promise<AddMembersResponse> {
  return apiRequest("/members", {
    method: "POST",
    body: JSON.stringify({
      members,
      consent_confirmed: consentConfirmed,
    }),
  });
}

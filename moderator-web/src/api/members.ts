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

export type GroupMember = {
  member_id: string;
  membership_id: string;
  phone_number: string;
  name: string | null;
  role: string;
  status: string;
  joined_at: string | null;
  created_at: string;
  updated_at: string;
};

/** The fields a moderator may change on a member card. */
export type MemberEdit = {
  name: string;
  phone_number: string;
  role: string;
  status: string;
};

export function listMembers(): Promise<GroupMember[]> {
  return apiRequest("/members");
}

export function updateMember(
  membershipId: string,
  edit: MemberEdit,
): Promise<GroupMember> {
  return apiRequest(`/members/${membershipId}`, {
    method: "PATCH",
    body: JSON.stringify(edit),
  });
}

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

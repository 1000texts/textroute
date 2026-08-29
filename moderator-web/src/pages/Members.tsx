import { useEffect, useState } from "react";
import {
  listMembers,
  updateMember,
  type GroupMember,
  type MemberEdit,
} from "../api/members";
import { Field } from "../components/Field";
import { useSession } from "../auth/SessionContext";

// Values permitted by the group_memberships role/status check constraints.
const ROLES = ["member", "moderator"];
const STATUSES = ["active", "removed"];

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function draftFrom(member: GroupMember): MemberEdit {
  return {
    name: member.name ?? "",
    phone_number: member.phone_number,
    role: member.role,
    status: member.status,
  };
}

export function Members() {
  const { session } = useSession();
  const [members, setMembers] = useState<GroupMember[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only one card is editable at a time, so a single draft is enough.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<MemberEdit | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function loadMembers() {
    setBusy(true);
    setError(null);
    try {
      setMembers(await listMembers());
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to load members",
      );
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadMembers();
  }, []);

  function startEdit(member: GroupMember) {
    setEditingId(member.membership_id);
    setDraft(draftFrom(member));
    setSaveError(null);
  }

  function cancelEdit() {
    // Discarding the draft is what restores the original values: the member
    // list itself was never modified.
    setEditingId(null);
    setDraft(null);
    setSaveError(null);
  }

  function updateDraft(field: keyof MemberEdit, value: string) {
    setDraft((current) => (current ? { ...current, [field]: value } : current));
  }

  async function saveEdit() {
    if (!draft || !editingId) return;

    if (!draft.name.trim() || !draft.phone_number.trim()) {
      setSaveError("Name and phone number are required.");
      return;
    }

    setSaving(true);
    setSaveError(null);
    try {
      const saved = await updateMember(editingId, {
        ...draft,
        name: draft.name.trim(),
        phone_number: draft.phone_number.trim(),
      });
      // Show what the server stored, not the draft: it normalizes the phone
      // number and stamps updated_at.
      setMembers((current) =>
        current.map((existing) =>
          existing.membership_id === saved.membership_id ? saved : existing,
        ),
      );
      setEditingId(null);
      setDraft(null);
    } catch (requestError) {
      // Stay in edit mode so the moderator's typing is not lost.
      setSaveError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to save member",
      );
    } finally {
      setSaving(false);
    }
  }

  const activeCount = members.filter(
    (member) => member.status === "active",
  ).length;

  return (
    <main className="frame frame-top">
      <h1 className="brand">TextRoute</h1>
      <h2 className="page-title">Members</h2>
      <p className="group-context">
        {session?.group_name} · {session?.group_phone_number}
      </p>

      <button
        className="text-button"
        type="button"
        disabled={busy || saving}
        onClick={() => void loadMembers()}
      >
        [ {busy ? "Loading..." : "Refresh"} ]
      </button>

      {error && <p className="message error">{error}</p>}

      {!error && members.length === 0 && !busy && (
        <p className="message">No members in this group yet.</p>
      )}

      {members.length > 0 && (
        <section className="members">
          <p className="section-label">
            {activeCount} active of {members.length} member
            {members.length === 1 ? "" : "s"}
          </p>
          <ul className="member-directory">
            {members.map((member) => {
              const editing = editingId === member.membership_id;
              // Non-active members stay listed, dimmed, so they can be
              // reactivated. They receive no routed messages.
              const inactive = member.status !== "active";

              return (
                <li
                  className={
                    inactive ? "member-card member-inactive" : "member-card"
                  }
                  key={member.membership_id}
                >
                  {editing && draft ? (
                    <>
                      <Field
                        id={`name-${member.membership_id}`}
                        label="Name"
                        value={draft.name}
                        onChange={(value) => updateDraft("name", value)}
                      />
                      <Field
                        id={`phone-${member.membership_id}`}
                        label="Phone number"
                        value={draft.phone_number}
                        onChange={(value) =>
                          updateDraft("phone_number", value)
                        }
                      />
                      <label
                        className="field"
                        htmlFor={`role-${member.membership_id}`}
                      >
                        <span>Role</span>
                        <select
                          id={`role-${member.membership_id}`}
                          value={draft.role}
                          onChange={(e) => updateDraft("role", e.target.value)}
                        >
                          {ROLES.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label
                        className="field"
                        htmlFor={`status-${member.membership_id}`}
                      >
                        <span>Status</span>
                        <select
                          id={`status-${member.membership_id}`}
                          value={draft.status}
                          onChange={(e) =>
                            updateDraft("status", e.target.value)
                          }
                        >
                          {STATUSES.map((status) => (
                            <option key={status} value={status}>
                              {status}
                            </option>
                          ))}
                        </select>
                      </label>
                    </>
                  ) : (
                    <>
                      <span className="member-name">
                        {member.name?.trim() || "Unnamed"}
                      </span>
                      <span className="member-phone">
                        {member.phone_number}
                      </span>
                      <span className="member-meta">
                        {member.role} · {member.status}
                      </span>
                    </>
                  )}

                  <span className="member-meta">
                    joined {formatTimestamp(member.joined_at)}
                  </span>
                  <span className="member-meta">
                    created {formatTimestamp(member.created_at)}
                  </span>
                  <span className="member-meta">
                    updated {formatTimestamp(member.updated_at)}
                  </span>

                  <div className="member-actions">
                    {editing ? (
                      <>
                        <button
                          className="text-button"
                          type="button"
                          disabled={saving}
                          onClick={() => void saveEdit()}
                        >
                          [ {saving ? "Saving..." : "Save"} ]
                        </button>
                        <button
                          className="text-button"
                          type="button"
                          disabled={saving}
                          onClick={cancelEdit}
                        >
                          [ Cancel ]
                        </button>
                      </>
                    ) : (
                      <button
                        className="text-button"
                        type="button"
                        disabled={editingId !== null || busy}
                        onClick={() => startEdit(member)}
                      >
                        [ Edit ]
                      </button>
                    )}
                  </div>

                  {editing && saveError && (
                    <p className="message error">{saveError}</p>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </main>
  );
}

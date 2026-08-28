import { useEffect, useState } from "react";
import { listMembers, type GroupMember } from "../api/members";
import { useSession } from "../auth/SessionContext";

function formatJoinedAt(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function Members() {
  const { session } = useSession();
  const [members, setMembers] = useState<GroupMember[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        disabled={busy}
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
            {members.length} member{members.length === 1 ? "" : "s"}
          </p>
          <ul className="member-directory">
            {members.map((member) => (
              <li className="member-card" key={member.membership_id}>
                <span className="member-name">
                  {member.name?.trim() || "Unnamed"}
                </span>
                <span className="member-phone">{member.phone_number}</span>
                <span className="member-meta">
                  {member.role} · {member.status}
                </span>
                <span className="member-meta">
                  joined {formatJoinedAt(member.joined_at)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

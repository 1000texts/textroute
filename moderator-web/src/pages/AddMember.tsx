import { useState, type FormEvent } from "react";
import { addMembers, type MemberInput } from "../api/members";
import { useSession } from "../auth/SessionContext";

const emptyMember = (): MemberInput => ({ phone_number: "", name: "" });

export function AddMember() {
  const { session } = useSession();
  const [members, setMembers] = useState<MemberInput[]>([emptyMember()]);
  const [consentConfirmed, setConsentConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function updateMember(
    index: number,
    field: keyof MemberInput,
    value: string,
  ) {
    setMembers((current) =>
      current.map((member, memberIndex) =>
        memberIndex === index ? { ...member, [field]: value } : member,
      ),
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (
      members.some(
        (member) => !member.phone_number.trim() || !member.name.trim(),
      )
    ) {
      setError("Every member needs a phone number and name.");
      return;
    }
    if (!consentConfirmed) {
      setError("Consent confirmation is required.");
      return;
    }

    setSubmitting(true);
    setStatus(null);
    setError(null);
    try {
      const result = await addMembers(
        members.map((member) => ({
          phone_number: member.phone_number.trim(),
          name: member.name.trim(),
        })),
        consentConfirmed,
      );
      setStatus(
        `Added ${result.members.length} member${
          result.members.length === 1 ? "" : "s"
        } to ${session?.group_name ?? "the group"}.`,
      );
      setMembers([emptyMember()]);
      setConsentConfirmed(false);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not add members.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="frame">
      <h1 className="brand">TextRoute</h1>
      <h2 className="page-title">Add Member</h2>
      <p className="group-context">
        {session?.group_name} · {session?.group_phone_number}
      </p>

      <form className="form member-form" onSubmit={onSubmit}>
        <div className="member-list">
          {members.map((member, index) => (
            <div className="member-row" key={index}>
              <label className="field">
                <span>Phone number {index + 1}</span>
                <input
                  type="tel"
                  value={member.phone_number}
                  placeholder="+1 555 123 4567"
                  onChange={(event) =>
                    updateMember(index, "phone_number", event.target.value)
                  }
                  autoComplete="tel"
                />
              </label>
              <label className="field">
                <span>Name {index + 1}</span>
                <input
                  type="text"
                  value={member.name}
                  onChange={(event) =>
                    updateMember(index, "name", event.target.value)
                  }
                  autoComplete="name"
                />
              </label>
              {members.length > 1 && (
                <button
                  className="remove-member"
                  type="button"
                  aria-label={`Remove member ${index + 1}`}
                  onClick={() =>
                    setMembers((current) =>
                      current.filter((_, memberIndex) => memberIndex !== index),
                    )
                  }
                >
                  [ remove ]
                </button>
              )}
            </div>
          ))}
        </div>

        <button
          className="add-more"
          type="button"
          onClick={() => setMembers((current) => [...current, emptyMember()])}
        >
          + add more
        </button>

        <label className="consent">
          <input
            type="checkbox"
            checked={consentConfirmed}
            required
            onChange={(event) => setConsentConfirmed(event.target.checked)}
          />
          <span>
          I confirm that I have received consent from each person listed above to include their phone number in this texting group and send them group messages.
          </span>
        </label>

        <button className="submit" type="submit" disabled={submitting}>
          [ {submitting ? "Submitting..." : "Submit"} ]
        </button>
      </form>

      {status && <p className="message">{status}</p>}
      {error && <p className="message error">{error}</p>}
    </main>
  );
}

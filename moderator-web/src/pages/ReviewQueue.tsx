import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  addGroupMember,
  approveMessage,
  fetchMessage,
  fetchModerationQueue,
  rejectMessage,
  type ModerationMessage,
} from "../api/groups";
import { Field } from "../components/Field";

type Props = {
  initialGroupId?: string;
};

export function ReviewQueue({ initialGroupId = "" }: Props) {
  const [groupId, setGroupId] = useState(initialGroupId);
  const [queue, setQueue] = useState<ModerationMessage[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ModerationMessage | null>(null);
  const [selectedRecipients, setSelectedRecipients] = useState<Set<string>>(
    new Set(),
  );
  const [memberName, setMemberName] = useState("");
  const [memberPhone, setMemberPhone] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selectedCount = selectedRecipients.size;

  const eligible = useMemo(
    () => detail?.eligible_recipients ?? detail?.suggested_recipients ?? [],
    [detail],
  );

  async function loadQueue(id: string) {
    setBusy(true);
    setError(null);
    try {
      const items = await fetchModerationQueue(id);
      setQueue(items);
      setStatus(`${items.length} awaiting review`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load queue");
    } finally {
      setBusy(false);
    }
  }

  async function openMessage(messageId: string) {
    setBusy(true);
    setError(null);
    try {
      const message = await fetchMessage(messageId);
      setSelectedId(messageId);
      setDetail(message);
      const suggested = new Set(
        (message.eligible_recipients ?? [])
          .filter((m) => m.suggested)
          .map((m) => m.id),
      );
      if (suggested.size === 0) {
        for (const s of message.suggested_recipients) {
          suggested.add(s.id);
        }
      }
      setSelectedRecipients(suggested);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load message");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (initialGroupId.trim()) {
      void loadQueue(initialGroupId.trim());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialGroupId]);

  async function onLoadQueue(e: FormEvent) {
    e.preventDefault();
    if (!groupId.trim()) {
      setError("Group id is required.");
      return;
    }
    setDetail(null);
    setSelectedId(null);
    await loadQueue(groupId.trim());
  }

  function toggleRecipient(id: string) {
    setSelectedRecipients((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onApprove() {
    if (!detail) return;
    if (selectedRecipients.size === 0) {
      setError("Select at least one recipient.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await approveMessage(detail.id, [...selectedRecipients]);
      setStatus(
        `Sent to ${result.delivered_outbound_ids?.length ?? 0} people (${result.workflow_status})`,
      );
      setDetail(null);
      setSelectedId(null);
      await loadQueue(groupId.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approve failed");
    } finally {
      setBusy(false);
    }
  }

  async function onReject() {
    if (!detail) return;
    setBusy(true);
    setError(null);
    try {
      await rejectMessage(detail.id);
      setStatus("Rejected");
      setDetail(null);
      setSelectedId(null);
      await loadQueue(groupId.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setBusy(false);
    }
  }

  async function onAddMember(e: FormEvent) {
    e.preventDefault();
    if (!groupId.trim() || !memberPhone.trim()) {
      setError("Group id and member phone are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addGroupMember(groupId.trim(), {
        phone_number: memberPhone.trim(),
        name: memberName.trim() || undefined,
      });
      setStatus("Member added");
      setMemberName("");
      setMemberPhone("");
      if (selectedId) await openMessage(selectedId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add member");
    } finally {
      setBusy(false);
    }
  }

  const senderLabel =
    detail?.sender?.name || detail?.sender?.phone_number || "Someone";

  return (
    <main className="frame frame-top">
      <h1 className="brand">TextRoute</h1>
      <h2 className="page-title">Moderator Review</h2>

      <form className="form" onSubmit={onLoadQueue}>
        <Field
          id="group-id"
          label="Group id"
          value={groupId}
          placeholder="uuid from create-group"
          onChange={setGroupId}
        />
        <button className="submit" type="submit" disabled={busy}>
          [ {busy ? "Loading..." : "Load Queue"} ]
        </button>
      </form>

      <form className="form secondary-form" onSubmit={onAddMember}>
        <p className="section-label">Add member (for testing the loop)</p>
        <Field
          id="member-name"
          label="Name (optional)"
          value={memberName}
          onChange={setMemberName}
        />
        <Field
          id="member-phone"
          label="Phone"
          value={memberPhone}
          placeholder="+1 555 222 3333"
          onChange={setMemberPhone}
        />
        <button className="submit" type="submit" disabled={busy}>
          [ Add Member ]
        </button>
      </form>

      {queue.length > 0 && (
        <section className="queue">
          <p className="section-label">Awaiting moderator</p>
          <ul className="queue-list">
            {queue.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={
                    selectedId === item.id ? "queue-item active" : "queue-item"
                  }
                  onClick={() => void openMessage(item.id)}
                >
                  <span className="queue-intent">{item.intent ?? "unknown"}</span>
                  <span className="queue-body">{item.body}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {detail && (
        <section className="review">
          <p className="section-label">
            {senderLabel} asked
            {detail.intent ? ` · ${detail.intent}` : ""}
            {detail.confidence != null
              ? ` · confidence ${detail.confidence.toFixed(2)}`
              : ""}
          </p>
          <blockquote className="message-body">“{detail.body}”</blockquote>

          {detail.constraints && Object.keys(detail.constraints).length > 0 && (
            <p className="constraints">
              {Object.entries(detail.constraints)
                .map(([k, v]) => `${k}: ${String(v)}`)
                .join(" · ")}
            </p>
          )}

          <p className="section-label">Suggested recipients</p>
          <ul className="recipient-list">
            {eligible.map((member) => {
              const checked = selectedRecipients.has(member.id);
              const label = member.name || member.phone_number;
              return (
                <li key={member.id}>
                  <label className="recipient">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleRecipient(member.id)}
                    />
                    <span>
                      {label}
                      {member.reason ? ` — ${member.reason}` : ""}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>

          <div className="actions">
            <button
              className="submit"
              type="button"
              disabled={busy}
              onClick={() => void onApprove()}
            >
              [ Send to {selectedCount} {selectedCount === 1 ? "person" : "people"} ]
            </button>
            <button
              className="submit danger"
              type="button"
              disabled={busy}
              onClick={() => void onReject()}
            >
              [ Reject ]
            </button>
          </div>
        </section>
      )}

      {status && <p className="message">{status}</p>}
      {error && <p className="message error">{error}</p>}
    </main>
  );
}

import { useEffect, useMemo, useState } from "react";
import {
  approveMessage,
  fetchMessage,
  fetchModerationQueue,
  rejectMessage,
  type ModerationMessage,
} from "../api/moderation";
import { useSession } from "../auth/SessionContext";

export function ReviewQueue() {
  const { session } = useSession();
  const [queue, setQueue] = useState<ModerationMessage[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ModerationMessage | null>(null);
  const [selectedRecipients, setSelectedRecipients] = useState<Set<string>>(
    new Set(),
  );
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const eligible = useMemo(
    () => detail?.eligible_recipients ?? detail?.suggested_recipients ?? [],
    [detail],
  );

  async function loadQueue() {
    setBusy(true);
    setError(null);
    try {
      const items = await fetchModerationQueue();
      setQueue(items);
      setStatus(`${items.length} awaiting review`);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to load queue",
      );
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
          .filter((member) => member.suggested)
          .map((member) => member.id),
      );
      if (suggested.size === 0) {
        for (const member of message.suggested_recipients) {
          suggested.add(member.id);
        }
      }
      setSelectedRecipients(suggested);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to load message",
      );
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadQueue();
  }, []);

  function toggleRecipient(id: string) {
    setSelectedRecipients((current) => {
      const next = new Set(current);
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
        `Sent to ${result.delivered_outbound_ids?.length ?? 0} people ` +
          `(${result.workflow_status})`,
      );
      setDetail(null);
      setSelectedId(null);
      await loadQueue();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Approve failed",
      );
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
      await loadQueue();
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Reject failed",
      );
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
      <p className="group-context">
        {session?.group_name} · {session?.group_phone_number}
      </p>

      <button
        className="text-button"
        type="button"
        disabled={busy}
        onClick={() => void loadQueue()}
      >
        [ {busy ? "Loading..." : "Refresh queue"} ]
      </button>

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
                .map(([key, value]) => `${key}: ${String(value)}`)
                .join(" · ")}
            </p>
          )}

          <p className="section-label">Suggested recipients</p>
          <ul className="recipient-list">
            {eligible.map((member) => (
              <li key={member.id}>
                <label className="recipient">
                  <input
                    type="checkbox"
                    checked={selectedRecipients.has(member.id)}
                    onChange={() => toggleRecipient(member.id)}
                  />
                  <span>
                    {member.name || member.phone_number}
                    {member.reason ? ` — ${member.reason}` : ""}
                  </span>
                </label>
              </li>
            ))}
          </ul>

          <div className="actions">
            <button
              className="submit"
              type="button"
              disabled={busy}
              onClick={() => void onApprove()}
            >
              [ Send to {selectedRecipients.size}{" "}
              {selectedRecipients.size === 1 ? "person" : "people"} ]
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

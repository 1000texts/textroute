import { useEffect, useMemo, useState } from "react";
import { getGroupSettings } from "../api/groups";
import {
  approveMessage,
  fetchMessage,
  fetchModerationQueue,
  listMessages,
  rejectMessage,
  type ModerationMessage,
} from "../api/moderation";
import { useSession } from "../auth/SessionContext";
import {
  formatTime,
  isFailure,
  isUnsettled,
  kindLabel,
  needsReview,
  policyLabel,
  routingLabel,
  statusLabel,
} from "../messages/labels";

type Tab = "review" | "all";

export function Messages() {
  const { session } = useSession();
  const [tab, setTab] = useState<Tab>("review");
  const [queue, setQueue] = useState<ModerationMessage[]>([]);
  const [all, setAll] = useState<ModerationMessage[]>([]);
  const [policy, setPolicy] = useState<string | undefined>(undefined);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ModerationMessage | null>(null);
  const [selectedRecipients, setSelectedRecipients] = useState<Set<string>>(
    new Set(),
  );
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const rows = tab === "review" ? queue : all;

  const eligible = useMemo(
    () => detail?.eligible_recipients ?? detail?.suggested_recipients ?? [],
    [detail],
  );

  // Both lists load together so the Needs Review count stays truthful even
  // while the All tab is showing. The queue endpoint remains the source of
  // truth for that count; it is never derived from the All list.
  async function loadAll() {
    setBusy(true);
    setError(null);
    try {
      const [queueItems, allItems] = await Promise.all([
        fetchModerationQueue(),
        listMessages(),
      ]);
      setQueue(queueItems);
      setAll(allItems);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to load messages",
      );
    } finally {
      setBusy(false);
    }
  }

  async function loadPolicy() {
    try {
      setPolicy((await getGroupSettings()).routing_policy);
    } catch {
      setPolicy(undefined);
    }
  }

  useEffect(() => {
    void loadAll();
    void loadPolicy();
  }, []);

  async function openMessage(messageId: string) {
    if (selectedId === messageId) {
      setSelectedId(null);
      setDetail(null);
      return;
    }
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
      // Report the server's status rather than assuming success: fan-out can
      // partially fail, and the client cannot predict the outcome.
      setStatus(
        `Sent to ${result.delivered_outbound_ids?.length ?? 0} people · ` +
          statusLabel(result).toLowerCase(),
      );
      setDetail(null);
      setSelectedId(null);
      await loadAll();
    } catch (requestError) {
      // Leave the panel open so the moderator can retry or adjust recipients.
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
      await loadAll();
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
  const awaitingApproval = detail != null && needsReview(detail);

  return (
    <main className="frame frame-top">
      <h1 className="brand">TextRoute</h1>
      <h2 className="page-title">Messages</h2>
      <p className="group-context">
        {session?.group_name} · {session?.group_phone_number}
        {policy ? ` · Routing: ${policyLabel(policy)}` : ""}
      </p>

      <div className="tabs">
        <button
          type="button"
          className={tab === "review" ? "tab active" : "tab"}
          onClick={() => setTab("review")}
        >
          [ Needs Review ({queue.length}) ]
        </button>
        <button
          type="button"
          className={tab === "all" ? "tab active" : "tab"}
          onClick={() => setTab("all")}
        >
          [ All Messages ({all.length}) ]
        </button>
        <button
          className="text-button"
          type="button"
          disabled={busy}
          onClick={() => void loadAll()}
        >
          [ {busy ? "Loading..." : "Refresh"} ]
        </button>
      </div>

      {error && <p className="message error">{error}</p>}

      {!busy && rows.length === 0 && (
        <p className="message">
          {tab === "review"
            ? "Nothing is waiting for your approval."
            : "No messages in this group yet."}
        </p>
      )}

      {rows.length > 0 && (
        <section className="queue">
          <ul className="queue-list">
            {rows.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={
                    selectedId === item.id ? "queue-item active" : "queue-item"
                  }
                  onClick={() => void openMessage(item.id)}
                >
                  <span className="row-meta">
                    <span>{formatTime(item.created_at)}</span>
                    <span>
                      {item.sender?.name || item.sender?.phone_number || "—"}
                    </span>
                    <span>{kindLabel(item)}</span>
                    <span>{routingLabel(item)}</span>
                    <span
                      className={
                        needsReview(item)
                          ? "pill attention"
                          : isFailure(item)
                            ? "pill failure"
                            : isUnsettled(item)
                              ? "pill unsettled"
                              : "pill"
                      }
                    >
                      {statusLabel(item)}
                    </span>
                  </span>
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
            {senderLabel} · {kindLabel(detail)} · {statusLabel(detail)}
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

          {awaitingApproval ? (
            <>
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
            </>
          ) : (
            <>
              {/* No approval controls: this message was never queued for a
                  human, or has already been acted on. */}
              {detail.routed_recipients.length > 0 ? (
                <>
                  <p className="section-label">Sent to</p>
                  <ul className="recipient-list">
                    {detail.routed_recipients.map((member) => (
                      <li className="recipient-static" key={member.id}>
                        {member.name || member.phone_number}
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="message">
                  {detail.kind === "reply"
                    ? "Replies are recorded but not routed."
                    : "No recipients recorded for this message."}
                </p>
              )}
            </>
          )}
        </section>
      )}

      {status && <p className="message">{status}</p>}
    </main>
  );
}

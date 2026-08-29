import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getGroupSettings } from "../api/groups";
import {
  fetchMessage,
  listMessages,
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

/**
 * The flat feed of inbound messages, kept for looking at what actually arrived.
 *
 * Read-only by design. Requests are the workflow objects, so approving lives on
 * the request detail where the moderator can see the whole conversation before
 * deciding. A message here that needs review links through to it.
 */
export function Messages() {
  const { session } = useSession();
  const [rows, setRows] = useState<ModerationMessage[]>([]);
  const [policy, setPolicy] = useState<string | undefined>(undefined);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ModerationMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadAll() {
    setBusy(true);
    setError(null);
    try {
      setRows(await listMessages());
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
      setDetail(await fetchMessage(messageId));
      setSelectedId(messageId);
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

  const senderLabel =
    detail?.sender?.name || detail?.sender?.phone_number || "Someone";

  return (
    <main className="frame frame-top">
      <h1 className="brand">TextRoute</h1>
      <h2 className="page-title">Message feed</h2>
      <p className="group-context">
        {session?.group_name} · {session?.group_phone_number}
        {policy ? ` · Routing: ${policyLabel(policy)}` : ""}
      </p>

      <div className="tabs">
        <span className="tab active">[ All messages ({rows.length}) ]</span>
        <Link className="tab" to="/requests">
          [ Requests ]
        </Link>
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
        <p className="message">No messages in this group yet.</p>
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
              {detail.kind === "member_reply"
                ? "Replies are recorded into their request, not re-routed."
                : "No recipients recorded for this message."}
            </p>
          )}

          {detail.request_id != null && (
            <p className="message">
              <Link to={`/requests/${detail.request_id}`}>
                {needsReview(detail)
                  ? "Open its request to review and approve"
                  : "Open its request to see the whole conversation"}
              </Link>
            </p>
          )}
        </section>
      )}
    </main>
  );
}

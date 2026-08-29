import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  approveMessage,
  fetchMessage,
  fetchModerationQueue,
  rejectMessage,
  type MemberBrief,
  type ModerationMessage,
} from "../api/moderation";
import {
  cancelRequest,
  completeRequest,
  fetchRequest,
  listRequests,
  sendRequestMessage,
  type RequestDetail,
  type RequestEvent,
  type RequestSummary,
  type ThreadMessage,
} from "../api/requests";
import { useSession } from "../auth/SessionContext";
import {
  closedAt,
  confidenceLabel,
  deliveryLabel,
  eventLabel,
  expiresInLabel,
  formatTime,
  kindLabel,
  lifecycleSteps,
  relativeTime,
  requestStatusLabel,
  requestTypeLabel,
} from "../messages/labels";

/**
 * The moderator's primary surface: requests are the workflow objects, and the
 * messages inside one are events in its lifecycle.
 *
 * Every entry point lands here — the lifecycle filters, the Needs Review
 * filter, and a deep link from the message feed — so there is one place that
 * knows how to read and act on a request.
 *
 * The three blocks answer three different questions in order: what is this
 * request, what are people saying, and what happened technically. Messages and
 * events are never mixed: a delivery is not something a person said.
 */

/**
 * Needs Review is deliberately not one of these.
 *
 * It is not a request status — a request can be open and awaiting approval, or
 * open and not — so treating it as a sixth lifecycle value would imply an
 * exclusivity that does not exist.
 */
const LIFECYCLE_FILTERS = [
  "open",
  "completed",
  "cancelled",
  "expired",
  "all",
] as const;

type LifecycleFilter = (typeof LIFECYCLE_FILTERS)[number];
type Filter = LifecycleFilter | "needs_review";

/** Status order for the grouped list: live work first. */
const STATUS_ORDER = ["open", "completed", "cancelled", "expired"];

export function Requests() {
  const { session } = useSession();
  const { requestId } = useParams();
  const navigate = useNavigate();

  const [rows, setRows] = useState<RequestSummary[]>([]);
  const [queue, setQueue] = useState<ModerationMessage[]>([]);
  const [filter, setFilter] = useState<Filter>("open");
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  // The message awaiting approval, loaded separately because only the message
  // endpoint knows who is eligible to receive it.
  const [pending, setPending] = useState<ModerationMessage | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selectedId = requestId ? Number(requestId) : null;

  /**
   * Requests and the review queue load together.
   *
   * The queue endpoint stays the source of truth for the Needs Review count;
   * it is never counted from the request list.
   */
  const loadList = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [requests, queueItems] = await Promise.all([
        listRequests(),
        fetchModerationQueue(),
      ]);
      setRows(requests);
      setQueue(queueItems);
    } catch (requestError) {
      setError(messageOf(requestError, "Failed to load requests"));
    } finally {
      setBusy(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    setBusy(true);
    setError(null);
    try {
      const loaded = await fetchRequest(id);
      setDetail(loaded);

      // A thread message waiting on a human means this request needs a
      // decision, so fetch that message for its eligible recipients.
      const awaiting = loaded.messages.find(
        (message) => message.workflow_status === "awaiting_moderator",
      );
      if (!awaiting) {
        setPending(null);
        setChosen(new Set());
        return;
      }
      const message = await fetchMessage(awaiting.id);
      setPending(message);
      setChosen(suggestedIds(message));
    } catch (requestError) {
      setError(messageOf(requestError, "Failed to load request"));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      setPending(null);
      return;
    }
    setDraft("");
    void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  /** Reload everything the action could have changed, including the count. */
  async function refreshAfterAction(id: number) {
    await Promise.all([loadDetail(id), loadList()]);
  }

  function selectRequest(id: number) {
    navigate(id === selectedId ? "/requests" : `/requests/${id}`);
  }

  async function onSend() {
    if (!detail || !draft.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await sendRequestMessage(detail.id, draft.trim());
      setDraft("");
      setStatus(
        result.failures.length > 0
          ? `Sent to ${result.sent_message_ids.length}, ${result.failures.length} failed`
          : `Sent to ${result.sent_message_ids.length} ${
              result.sent_message_ids.length === 1 ? "person" : "people"
            }`,
      );
      await refreshAfterAction(detail.id);
    } catch (requestError) {
      setError(messageOf(requestError, "Send failed"));
    } finally {
      setBusy(false);
    }
  }

  async function onApprove() {
    if (!detail || !pending) return;
    if (chosen.size === 0) {
      setError("Select at least one recipient.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await approveMessage(pending.id, [...chosen]);
      // Report what the server did rather than assuming success: a fan-out can
      // partially fail and the client cannot predict the outcome.
      setStatus(
        `Sent to ${result.delivered_outbound_ids?.length ?? 0} people`,
      );
      await refreshAfterAction(detail.id);
    } catch (requestError) {
      // Stay in place so the moderator can adjust recipients and retry.
      setError(messageOf(requestError, "Approve failed"));
    } finally {
      setBusy(false);
    }
  }

  async function onReject() {
    if (!detail || !pending) return;
    setBusy(true);
    setError(null);
    try {
      await rejectMessage(pending.id);
      setStatus("Rejected");
      await refreshAfterAction(detail.id);
    } catch (requestError) {
      setError(messageOf(requestError, "Reject failed"));
    } finally {
      setBusy(false);
    }
  }

  async function onResolve(action: "complete" | "cancel") {
    if (!detail) return;
    if (
      !window.confirm(
        `Mark this request ${action === "complete" ? "complete" : "cancelled"}? ` +
          "Later messages from these members will start a new request.",
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated =
        action === "complete"
          ? await completeRequest(detail.id)
          : await cancelRequest(detail.id);
      setStatus(`Request ${requestStatusLabel(updated.status).toLowerCase()}`);
      await refreshAfterAction(detail.id);
    } catch (requestError) {
      setError(messageOf(requestError, `Could not ${action} request`));
    } finally {
      setBusy(false);
    }
  }

  // Requests with a message awaiting approval, per the queue endpoint.
  const reviewRequestIds = useMemo(
    () =>
      new Set(
        queue
          .map((item) => item.request_id)
          .filter((id): id is number => id != null),
      ),
    [queue],
  );

  const visible = useMemo(() => {
    if (filter === "needs_review") {
      return rows.filter((row) => reviewRequestIds.has(row.id));
    }
    if (filter === "all") return rows;
    return rows.filter((row) => row.status === filter);
  }, [rows, filter, reviewRequestIds]);

  const grouped = useMemo(() => {
    const buckets = new Map<string, RequestSummary[]>();
    for (const row of visible) {
      const bucket = buckets.get(row.status) ?? [];
      bucket.push(row);
      buckets.set(row.status, bucket);
    }
    return STATUS_ORDER.filter((s) => buckets.has(s)).map((s) => ({
      status: s,
      items: buckets.get(s) as RequestSummary[],
    }));
  }, [visible]);

  return (
    <main className="frame frame-top">
      <h1 className="brand">TextRoute</h1>
      <h2 className="page-title">Requests</h2>
      <p className="group-context">
        {session?.group_name} · {session?.group_phone_number}
      </p>

      {error && <p className="message error">{error}</p>}

      <div className="workbench">
        <section className="request-list">
          <div>
            <p className="pane-heading">Requests</p>
            <button
              type="button"
              className={
                "review-filter" +
                (filter === "needs_review" ? " active" : "") +
                (queue.length === 0 ? " empty" : "")
              }
              onClick={() => setFilter("needs_review")}
            >
              [ Needs Review {queue.length} ]
            </button>
          </div>

          <div>
            <p className="pane-heading">Lifecycle</p>
            <div className="lifecycle-filters">
              {LIFECYCLE_FILTERS.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={filter === value ? "tab active" : "tab"}
                  onClick={() => setFilter(value)}
                >
                  [ {value === "all" ? "All" : requestStatusLabel(value)} ]
                </button>
              ))}
            </div>
          </div>

          <button
            className="text-button"
            type="button"
            disabled={busy}
            onClick={() => void loadList()}
          >
            [ {busy ? "Loading..." : "Refresh"} ]
          </button>

          {!busy && visible.length === 0 && (
            <p className="message">
              {filter === "needs_review"
                ? "Nothing is waiting for your approval."
                : "No requests to show."}
            </p>
          )}

          {grouped.map((group) => (
            <div className="status-group" key={group.status}>
              <span className="status-group-label">
                {requestStatusLabel(group.status)}
              </span>
              {group.items.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className={
                    "request-card" +
                    (item.id === selectedId ? " active" : "") +
                    (reviewRequestIds.has(item.id) ? " attention" : "")
                  }
                  onClick={() => selectRequest(item.id)}
                >
                  <span className="request-card-title">
                    {item.summary ?? "(no summary)"}
                  </span>
                  <span className="request-card-meta">
                    {memberName(item.requester)}
                  </span>
                  <span className="request-card-meta">
                    {participantsLabel(item.participant_count)}
                    {" · "}
                    {relativeTime(item.last_activity_at ?? item.created_at)}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </section>

        <section>
          {detail ? (
            <RequestPanel
              detail={detail}
              pending={pending}
              chosen={chosen}
              draft={draft}
              busy={busy}
              onToggleRecipient={(id) =>
                setChosen((current) => toggled(current, id))
              }
              onDraftChange={setDraft}
              onSend={() => void onSend()}
              onApprove={() => void onApprove()}
              onReject={() => void onReject()}
              onResolve={(action) => void onResolve(action)}
            />
          ) : (
            <p className="message">
              Select a request to read its conversation.
            </p>
          )}
        </section>
      </div>

      {status && <p className="message">{status}</p>}
    </main>
  );
}

type PanelProps = {
  detail: RequestDetail;
  pending: ModerationMessage | null;
  chosen: Set<string>;
  draft: string;
  busy: boolean;
  onToggleRecipient: (id: string) => void;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onApprove: () => void;
  onReject: () => void;
  onResolve: (action: "complete" | "cancel") => void;
};

function RequestPanel({
  detail,
  pending,
  chosen,
  draft,
  busy,
  onToggleRecipient,
  onDraftChange,
  onSend,
  onApprove,
  onReject,
  onResolve,
}: PanelProps) {
  const isOpen = detail.status === "open";
  const ended = closedAt(detail);
  const expiry = isOpen ? expiresInLabel(detail.expires_at) : null;
  const eligible = pending?.eligible_recipients ?? pending?.suggested_recipients;
  const items = useMemo(() => groupThread(detail.messages), [detail.messages]);
  const filters = detail.extracted_filters ?? {};

  return (
    <>
      <div className="request-block">
        <span className="request-id">Request #{detail.id}</span>
        <h3 className="request-title">{detail.summary ?? "(no summary)"}</h3>

        <div className="lifecycle">
          {lifecycleSteps(detail.status).map((step, index) => (
            <span key={step.label} className={`lifecycle-step ${step.state}`}>
              {index > 0 ? "→ " : ""}
              {step.state === "done" ? "✓ " : step.state === "current" ? "● " : "○ "}
              {step.label}
            </span>
          ))}
          {expiry && <span>{expiry}</span>}
        </div>

        <dl className="request-facts">
          <dt>Requester</dt>
          <dd>{memberName(detail.requester)}</dd>

          <dt>Intent</dt>
          <dd>{requestTypeLabel(detail.request_type)}</dd>

          <dt>Confidence</dt>
          <dd>{confidenceLabel(detail.confidence)}</dd>

          {Object.keys(filters).length > 0 && (
            <>
              <dt>Filters</dt>
              <dd>
                {Object.entries(filters)
                  .map(([key, value]) => `${key}: ${String(value)}`)
                  .join(" · ")}
              </dd>
            </>
          )}

          <dt>Participants</dt>
          <dd>{detail.participant_count}</dd>

          <dt>Created</dt>
          <dd>{formatTime(detail.created_at)}</dd>

          {ended && (
            <>
              <dt>{requestStatusLabel(detail.status)}</dt>
              <dd>{formatTime(ended)}</dd>
            </>
          )}

          <dt>Analysis</dt>
          {/* Naming the model is how a reader tells a real analysis from the
              keyword fallback that runs when it is unavailable. */}
          <dd>{detail.model_name ?? "keywords"}</dd>
        </dl>
      </div>

      {pending && (
        <div className="needs-review-block">
          <p className="section-label">Needs review</p>
          <p className="section-label">Send to</p>
          <ul className="recipient-choices">
            {(eligible ?? []).map((member) => (
              <li key={member.id}>
                <label className="recipient">
                  <input
                    type="checkbox"
                    checked={chosen.has(member.id)}
                    onChange={() => onToggleRecipient(member.id)}
                  />
                  <span>
                    {memberName(member)}
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
              onClick={onApprove}
            >
              [ Approve · send to {chosen.size}{" "}
              {chosen.size === 1 ? "person" : "people"} ]
            </button>
            <button
              className="submit danger"
              type="button"
              disabled={busy}
              onClick={onReject}
            >
              [ Reject ]
            </button>
          </div>
        </div>
      )}

      <div className="request-block">
        <p className="section-label">Conversation</p>
        <ul className="thread">
          {items.map((item) =>
            item.type === "routing" ? (
              <li key={item.key}>
                <RoutingBlock group={item} events={detail.events} />
              </li>
            ) : (
              <li className="thread-message" key={item.message.id}>
                <span className="speaker">
                  <span className="speaker-name">
                    {attribution(item.message)}
                  </span>
                  <span className="speaker-kind">
                    {kindLabel(item.message)}
                  </span>
                  <span className="speaker-time">
                    {formatTime(item.message.created_at)}
                  </span>
                </span>
                <span className="queue-body">{item.message.body}</span>
              </li>
            ),
          )}
        </ul>
        {items.length === 0 && <p className="message">No messages yet.</p>}
      </div>

      <div className="request-block">
        <p className="section-label">Activity</p>
        {detail.events.length === 0 ? (
          <p className="message">Nothing recorded yet.</p>
        ) : (
          <ul className="activity-list">
            {detail.events.map((event) => (
              <li
                key={event.id}
                className={
                  event.event_type === "delivery_failed"
                    ? "activity-item failed"
                    : "activity-item"
                }
              >
                <span className="activity-time">
                  {formatTime(event.created_at)}
                </span>
                <span>
                  {event.event_type === "delivery_failed" ? "! " : "✓ "}
                  {eventLabel(event.event_type)}
                </span>
                {eventDetail(event) && <span>· {eventDetail(event)}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      {isOpen && (
        <div className="request-block">
          <p className="section-label">Reply to the requester</p>
          <div className="composer">
            <div className="field">
              <textarea
                rows={3}
                value={draft}
                placeholder="Which day works for you?"
                onChange={(event) => onDraftChange(event.target.value)}
              />
            </div>
            <div className="actions">
              <button
                className="submit"
                type="button"
                disabled={busy || !draft.trim()}
                onClick={onSend}
              >
                [ Send ]
              </button>
              <button
                className="submit"
                type="button"
                disabled={busy}
                onClick={() => onResolve("complete")}
              >
                [ Complete ]
              </button>
              <button
                className="submit danger"
                type="button"
                disabled={busy}
                onClick={() => onResolve("cancel")}
              >
                [ Cancel request ]
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/** One routing operation, collapsed. Expanding shows who it reached. */
function RoutingBlock({
  group,
  events,
}: {
  group: RoutingGroup;
  events: RequestEvent[];
}) {
  const [expanded, setExpanded] = useState(false);

  const recipients = useMemo(() => {
    const delivered = group.copies.map((copy) => ({
      key: copy.id,
      name: memberName(copy.member),
      outcome: outcomeFor(copy, events),
    }));

    // A failed send leaves no message row at all, so its recipient can only be
    // recovered from the event's payload. Failures carry no parent, so they are
    // only folded in when this request had a single routing operation; the
    // Activity block lists every one of them regardless.
    if (!group.soleOperation) return delivered;
    const failures = events
      .filter((event) => event.event_type === "delivery_failed")
      .map((event, index) => ({
        key: `failed-${event.id}-${index}`,
        name: memberLabelFromPayload(event, group.copies),
        outcome: "failed" as const,
      }));
    return [...delivered, ...failures];
  }, [group, events]);

  return (
    <div className="routing-block">
      <button
        type="button"
        className="routing-summary"
        onClick={() => setExpanded((value) => !value)}
      >
        ↗ Routed to {recipients.length}{" "}
        {recipients.length === 1 ? "member" : "members"}
        {expanded ? " [ hide ]" : " [ show ]"}
      </button>
      {expanded && (
        <ul className="routing-recipients">
          {recipients.map((recipient) => (
            <li
              className={`routing-recipient ${recipient.outcome}`}
              key={recipient.key}
            >
              <span>{recipient.outcome === "failed" ? "!" : "✓"}</span>
              <span>{recipient.name}</span>
              <span className="outcome">{deliveryLabel(recipient.outcome)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type RoutingGroup = {
  type: "routing";
  key: string;
  copies: ThreadMessage[];
  /** True when the request had exactly one routing operation. */
  soleOperation: boolean;
};

type ThreadItem = { type: "message"; message: ThreadMessage } | RoutingGroup;

/**
 * Collapse fan-out copies into their routing operation.
 *
 * The grouping key is `parent_message_id`: `fan_out()` stamps every copy with
 * the authorized message it is fanning out, which makes that column the
 * identity of the operation. Grouping by it rather than by adjacency means
 * interleaved messages cannot split one operation into two blocks, and two
 * genuine operations never merge into one.
 */
function groupThread(messages: ThreadMessage[]): ThreadItem[] {
  const groups = new Map<string, RoutingGroup>();
  const items: ThreadItem[] = [];

  for (const message of messages) {
    if (message.kind !== "fanout_copy") {
      items.push({ type: "message", message });
      continue;
    }
    const key = message.parent_message_id ?? `unparented-${message.id}`;
    const existing = groups.get(key);
    if (existing) {
      existing.copies.push(message);
      continue;
    }
    const group: RoutingGroup = {
      type: "routing",
      key,
      copies: [message],
      soleOperation: true,
    };
    groups.set(key, group);
    // Positioned at the first copy of the operation, keeping the thread in
    // chronological order.
    items.push(group);
  }

  if (groups.size > 1) {
    for (const group of groups.values()) group.soleOperation = false;
  }
  return items;
}

/**
 * What became of one fan-out copy.
 *
 * A `delivered` event names the copy in `message_id`, so it is the most direct
 * answer. The copy's own status is the fallback for rows written before events
 * existed.
 */
function outcomeFor(
  copy: ThreadMessage,
  events: RequestEvent[],
): "delivered" | "failed" | "unknown" {
  const event = events.find(
    (candidate) =>
      candidate.message_id === copy.id &&
      (candidate.event_type === "delivered" ||
        candidate.event_type === "delivery_failed"),
  );
  if (event) {
    return event.event_type === "delivered" ? "delivered" : "failed";
  }
  if (copy.workflow_status === "delivery_failed") return "failed";
  if (copy.workflow_status === "sent" || copy.workflow_status === "delivered") {
    return "delivered";
  }
  return "unknown";
}

/** A failed recipient is only identifiable through the event payload. */
function memberLabelFromPayload(
  event: RequestEvent,
  copies: ThreadMessage[],
): string {
  const memberId = event.payload.member_id;
  if (typeof memberId !== "string") return "A member";
  const known = copies.find((copy) => copy.member?.id === memberId);
  return known ? memberName(known.member) : "A member";
}

function eventDetail(event: RequestEvent): string | null {
  const by = event.payload.by;
  if (typeof by === "string") return by.replace(/_/g, " ");
  const error = event.payload.error;
  if (typeof error === "string") return error;
  return null;
}

/**
 * Who said this, to whom.
 *
 * Author and subject are different columns, so a moderator's clarification
 * reads "Moderator → Alice" instead of being attributed to Alice herself.
 */
function attribution(message: ThreadMessage): string {
  if (message.kind === "moderator_clarification") {
    return `${memberName(message.author)} (moderator) → ${memberName(
      message.member,
    )}`;
  }
  return memberName(message.author ?? message.member);
}

function memberName(member: MemberBrief | null | undefined): string {
  return member?.name || member?.phone_number || "—";
}

function participantsLabel(count: number): string {
  return `${count} ${count === 1 ? "participant" : "participants"}`;
}

function suggestedIds(message: ModerationMessage): Set<string> {
  const suggested = new Set(
    (message.eligible_recipients ?? [])
      .filter((member) => member.suggested)
      .map((member) => member.id),
  );
  if (suggested.size === 0) {
    for (const member of message.suggested_recipients) suggested.add(member.id);
  }
  return suggested;
}

function toggled(current: Set<string>, id: string): Set<string> {
  const next = new Set(current);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  return next;
}

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

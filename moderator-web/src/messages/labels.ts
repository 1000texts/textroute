/**
 * Moderator-facing wording for internal enum values.
 *
 * Keeps the UI decoupled from backend state names, and keeps the vocabulary
 * honest: the model suggests, the moderator approves, a group policy
 * authorizes, and RoutingService sends. Nothing here should imply a human
 * reviewed a message that no human saw.
 */
import type { ModerationMessage } from "../api/moderation";

/** Kind and Status are separate axes. "Reply" is a kind, never a status. */
export function kindLabel(message: { kind: string | null }): string {
  switch (message.kind) {
    case "original_request":
      return "Request";
    case "member_reply":
      return "Reply";
    case "moderator_clarification":
      return "Moderator";
    case "fanout_copy":
      return "Sent copy";
    case "confirmation":
      return "Confirmation";
    default:
      return "—";
  }
}

export function routingLabel(message: ModerationMessage): string {
  switch (message.routing_policy) {
    case "moderator_required":
      return "Moderator";
    case "auto_group":
      return "Automatic";
    case "auto_matched":
      return "Matched";
    default:
      // Replies are never policy-routed, so they carry no snapshot.
      return "—";
  }
}

export function statusLabel(message: ModerationMessage): string {
  switch (message.workflow_status) {
    case "awaiting_moderator":
      return "Awaiting approval";
    case "auto_authorized":
      return "Routing";
    case "approved":
      return "Approved";
    case "delivering":
      return "Sending";
    case "delivered":
      return "Delivered";
    case "partially_delivered":
      return "Partially delivered";
    case "delivery_failed":
      return "Delivery failed";
    case "processing_failed":
      return "Processing failed";
    case "moderator_rejected":
      return "Rejected";
    case "processing":
      return "Processing";
    default:
      return "Received";
  }
}

export function needsReview(message: ModerationMessage): boolean {
  return message.workflow_status === "awaiting_moderator";
}

/**
 * Mid-flight or failed states worth visually flagging.
 *
 * `auto_authorized` and `delivering` are transient and nothing reconciles
 * them: if the process dies mid fan-out the row stays there permanently, so
 * neither may be presented as success.
 */
export function isUnsettled(message: ModerationMessage): boolean {
  return (
    message.workflow_status === "auto_authorized" ||
    message.workflow_status === "delivering"
  );
}

export function isFailure(message: ModerationMessage): boolean {
  return (
    message.workflow_status === "delivery_failed" ||
    message.workflow_status === "processing_failed" ||
    message.workflow_status === "partially_delivered"
  );
}

export function policyLabel(routingPolicy: string | undefined): string {
  switch (routingPolicy) {
    case "auto_group":
      return "Automatic";
    case "moderator_required":
      return "Moderator approval required";
    case "auto_matched":
      return "Matched recipients";
    default:
      return "Unknown";
  }
}

export function requestStatusLabel(status: string): string {
  switch (status) {
    case "open":
      return "Open";
    case "completed":
      return "Completed";
    case "cancelled":
      return "Cancelled";
    case "expired":
      return "Expired";
    default:
      return status;
  }
}

export type LifecycleStep = {
  label: string;
  state: "done" | "current" | "pending";
};

/**
 * The request lifecycle as two stages: it opened, and then it closed somehow.
 *
 * Completed, cancelled, and expired are alternative endings rather than steps
 * along one path, so an open request shows a single unnamed second stage
 * instead of three pending ones it will never all reach.
 */
export function lifecycleSteps(status: string): LifecycleStep[] {
  if (status === "open") {
    return [
      { label: "Open", state: "current" },
      { label: "Closed", state: "pending" },
    ];
  }
  return [
    { label: "Open", state: "done" },
    { label: requestStatusLabel(status), state: "done" },
  ];
}

/** When a closed request ended, reading whichever timestamp applies. */
export function closedAt(request: {
  status: string;
  completed_at: string | null;
  cancelled_at: string | null;
  expires_at: string | null;
}): string | null {
  switch (request.status) {
    case "completed":
      return request.completed_at;
    case "cancelled":
      return request.cancelled_at;
    case "expired":
      // No expired_at column: status plus the expired event record the ending,
      // and expires_at already says when it was due.
      return request.expires_at;
    default:
      return null;
  }
}

/** Machine-generated activity, phrased for a person reading the trail. */
export function eventLabel(eventType: string): string {
  switch (eventType) {
    case "authorized":
      return "Routing authorized";
    case "delivered":
      return "Delivered";
    case "delivery_failed":
      return "Delivery failed";
    case "completed":
      return "Marked complete";
    case "cancelled":
      return "Cancelled";
    case "expired":
      return "Expired";
    default:
      return eventType;
  }
}

/** Request types come from the analyzer, so unseen values must still read well. */
export function requestTypeLabel(requestType: string | null): string {
  if (!requestType) return "—";
  const words = requestType.replace(/^request_/, "").replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function confidenceLabel(confidence: number | null): string {
  // Absent analysis is not zero confidence, so it must not render as "0%".
  if (confidence == null) return "—";
  return `${Math.round(confidence * 100)}%`;
}

/** "12 min ago", for a list where exact timestamps are noise. */
export function relativeTime(value: string | null): string {
  if (!value) return "—";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return value;

  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days}d ago`;
}

/**
 * How long an open request has left before the expiry sweep closes it.
 *
 * Only meaningful while open: a completed request keeps its expires_at, and
 * showing a countdown on it would suggest something is still pending.
 */
export function expiresInLabel(expiresAt: string | null): string | null {
  if (!expiresAt) return null;
  const due = new Date(expiresAt).getTime();
  if (Number.isNaN(due)) return null;

  const minutes = Math.round((due - Date.now()) / 60000);
  if (minutes <= 0) return "Past expiry";
  if (minutes < 60) return `Expires in ${minutes} min`;

  const hours = Math.round(minutes / 60);
  return `Expires in ${hours}h`;
}

/** Per-recipient fan-out outcome, phrased for a person. */
export function deliveryLabel(outcome: "delivered" | "failed" | "unknown"): string {
  switch (outcome) {
    case "delivered":
      return "Delivered";
    case "failed":
      return "Failed";
    default:
      return "No delivery recorded";
  }
}

export function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

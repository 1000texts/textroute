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
export function kindLabel(message: ModerationMessage): string {
  switch (message.kind) {
    case "reply":
      return "Reply";
    case "new_request":
      return "Request";
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

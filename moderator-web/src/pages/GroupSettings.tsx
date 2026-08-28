import { useEffect, useState } from "react";
import {
  getGroupSettings,
  updateRoutingPolicy,
  type GroupSettings as Settings,
} from "../api/groups";
import { useSession } from "../auth/SessionContext";

// auto_matched is intentionally absent: the backend reserves it but does not
// implement it, and the UI should not advertise a feature that does not exist.
const OPTIONS = [
  {
    value: "moderator_required",
    title: "Moderator approval required",
    description: "New requests wait for your approval before being sent.",
  },
  {
    value: "auto_group",
    title: "Automatic group routing",
    description:
      "New requests are sent automatically to the other active members.",
  },
];

export function GroupSettings() {
  const { session } = useSession();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [choice, setChoice] = useState<string>("moderator_required");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadSettings() {
    setBusy(true);
    setError(null);
    try {
      const current = await getGroupSettings();
      setSettings(current);
      setChoice(current.routing_policy);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to load settings",
      );
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void loadSettings();
  }, []);

  async function onSave() {
    // Turning moderation off is a significant behavior change, so confirm it.
    // Switching back to moderator_required is the safe direction and does not.
    if (choice === "auto_group" && settings?.routing_policy !== "auto_group") {
      const confirmed = window.confirm(
        "Enable automatic routing?\n\n" +
          "New requests will be sent to the other active group members " +
          "without moderator approval.",
      );
      if (!confirmed) return;
    }

    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const updated = await updateRoutingPolicy(choice);
      setSettings(updated);
      setChoice(updated.routing_policy);
      setStatus("Saved.");
    } catch (requestError) {
      setError(
        requestError instanceof Error ? requestError.message : "Save failed",
      );
    } finally {
      setBusy(false);
    }
  }

  const unchanged = settings?.routing_policy === choice;

  return (
    <main className="frame frame-top">
      <h1 className="brand">TextRoute</h1>
      <h2 className="page-title">Group Settings</h2>
      <p className="group-context">
        {session?.group_name} · {session?.group_phone_number}
      </p>

      <section className="settings">
        <p className="section-label">Message routing</p>

        <ul className="policy-list">
          {OPTIONS.map((option) => (
            <li key={option.value}>
              <label
                className={
                  choice === option.value
                    ? "policy-option active"
                    : "policy-option"
                }
              >
                <input
                  type="radio"
                  name="routing_policy"
                  value={option.value}
                  checked={choice === option.value}
                  onChange={() => setChoice(option.value)}
                />
                <span>
                  <span className="policy-title">{option.title}</span>
                  <span className="policy-description">
                    {option.description}
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>

        <p className="form-note">
          Changing this affects new requests only. Pending messages awaiting
          your approval are unaffected.
        </p>

        <div className="actions">
          <button
            className="submit"
            type="button"
            disabled={busy || unchanged}
            onClick={() => void onSave()}
          >
            [ {busy ? "Saving..." : "Save changes"} ]
          </button>
        </div>
      </section>

      {status && <p className="message">{status}</p>}
      {error && <p className="message error">{error}</p>}
    </main>
  );
}

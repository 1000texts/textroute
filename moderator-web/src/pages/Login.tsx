import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  requestModeratorChallenge,
  verifyModeratorChallenge,
  type ChallengeResponse,
} from "../api/auth";
import { useSession } from "../auth/SessionContext";
import { Field } from "../components/Field";

export function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { setAuthenticatedSession } = useSession();
  const [groupPhoneNumber, setGroupPhoneNumber] = useState("");
  const [moderatorPhoneNumber, setModeratorPhoneNumber] = useState("");
  const [challenge, setChallenge] = useState<ChallengeResponse | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function requestCode(event: FormEvent) {
    event.preventDefault();
    if (!groupPhoneNumber.trim() || !moderatorPhoneNumber.trim()) {
      setError("Group and moderator phone numbers are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      setChallenge(
        await requestModeratorChallenge({
          group_phone_number: groupPhoneNumber.trim(),
          moderator_phone_number: moderatorPhoneNumber.trim(),
        }),
      );
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not request a confirmation code.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function verifyCode(event: FormEvent) {
    event.preventDefault();
    if (!challenge || !/^\d{6}$/.test(code)) {
      setError("Enter the six-digit confirmation code.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const session = await verifyModeratorChallenge({
        challenge_id: challenge.challenge_id,
        code,
      });
      setAuthenticatedSession(session);
      const destination =
        (location.state as { from?: string } | null)?.from ?? "/add-member";
      navigate(destination, { replace: true });
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Could not verify the confirmation code.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="frame">
      <h1 className="brand">TextRoute</h1>
      <h2 className="page-title">Moderator Login</h2>

      {!challenge ? (
        <form className="form" onSubmit={requestCode}>
          <Field
            id="group-phone-number"
            label="Group inbound number"
            value={groupPhoneNumber}
            placeholder="+1 555 000 1001"
            onChange={setGroupPhoneNumber}
          />
          <Field
            id="moderator-phone-number"
            label="Your phone number"
            value={moderatorPhoneNumber}
            placeholder="+1 555 123 4567"
            onChange={setModeratorPhoneNumber}
          />
          <button className="submit" type="submit" disabled={submitting}>
            [ {submitting ? "Sending..." : "Send Confirmation Code"} ]
          </button>
        </form>
      ) : (
        <form className="form" onSubmit={verifyCode}>
          <p className="form-note">
            Enter the six-digit code sent to your moderator number.
          </p>
          {challenge.development_code && (
            <p className="development-code">
              Development code: {challenge.development_code}
            </p>
          )}
          <Field
            id="confirmation-code"
            label="Confirmation code"
            value={code}
            placeholder="000000"
            onChange={setCode}
          />
          <button className="submit" type="submit" disabled={submitting}>
            [ {submitting ? "Verifying..." : "Log In"} ]
          </button>
          <button
            className="text-button"
            type="button"
            onClick={() => {
              setChallenge(null);
              setCode("");
              setError(null);
            }}
          >
            [ Start over ]
          </button>
        </form>
      )}

      {error && <p className="message error">{error}</p>}
    </main>
  );
}

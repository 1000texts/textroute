import { useState, type FormEvent } from "react";
import { createGroup } from "../api/groups";
import { Field } from "../components/Field";

export function CreateGroup() {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !phoneNumber.trim()) {
      setError("Group name and phone number are required.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setStatus(null);

    try {
      const group = await createGroup({
        name: name.trim(),
        description: description.trim() ? description.trim() : null,
        moderator_phone_number: phoneNumber.trim(),
      });
      setStatus(`Created ${group.name} (${group.id})`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create group");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="frame">
      <h1 className="brand">TextRoute</h1>
      <h2 className="page-title">Create Your Group</h2>

      <form className="form" onSubmit={onSubmit}>
        <Field
          id="group-name"
          label="Group name"
          value={name}
          placeholder="Neighborhood"
          onChange={setName}
        />
        <Field
          id="group-description"
          label="Description (optional)"
          value={description}
          onChange={setDescription}
        />
        <Field
          id="phone-number"
          label="Your phone number"
          value={phoneNumber}
          placeholder="+1 555 123 4567"
          onChange={setPhoneNumber}
        />

        <button className="submit" type="submit" disabled={submitting}>
          [ {submitting ? "Creating..." : "Create Group"} ]
        </button>
      </form>

      {status && <p className="message">{status}</p>}
      {error && <p className="message error">{error}</p>}
    </main>
  );
}

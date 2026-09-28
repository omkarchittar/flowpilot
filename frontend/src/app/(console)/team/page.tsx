"use client";
import { useState } from "react";
import { Plus, ShieldCheck } from "lucide-react";
import { useAuth } from "@/components/auth";
import { api, errorMessage } from "@/lib/api";
import { useResource } from "@/lib/use-resource";
import type { Role, User } from "@/lib/types";
import {
  ErrorNotice,
  Loading,
  PageHeading,
  Panel,
  SuccessNotice,
} from "@/components/ui";
const roles: Role[] = ["requester", "reviewer", "approver", "admin"];
export default function Team() {
  const { session } = useAuth();
  const admin = session!.user.role === "admin";
  const resource = useResource<User[]>(admin ? "/admin/users" : null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [success, setSuccess] = useState<string>();
  if (!admin)
    return (
      <ErrorNotice message="Account administration is available to administrators." />
    );
  return (
    <>
      <PageHeading
        eyebrow="Workspace administration"
        title="Team & access"
        description="Give each person the access their work requires."
        action={
          <button
            className="button small"
            onClick={() => setOpen((value) => !value)}
          >
            <Plus size={16} />
            Create account
          </button>
        }
      />
      <ErrorNotice message={error ?? resource.error} retry={resource.refresh} />
      {success && <SuccessNotice>{success}</SuccessNotice>}
      {open && (
        <Panel
          title="Create an account"
          subtitle="Share the initial password securely with its owner. No email is sent."
        >
          <form
            className="form-body"
            onSubmit={async (event) => {
              event.preventDefault();
              const form = event.currentTarget;
              const data = Object.fromEntries(new FormData(form));
              setBusy(true);
              setError(undefined);
              setSuccess(undefined);
              try {
                await api(
                  "/admin/users",
                  { method: "POST", body: JSON.stringify(data) },
                  session!.csrf_token,
                );
                form.reset();
                setOpen(false);
                setSuccess(
                  "Account created. The owner can now sign in with the credentials you provided.",
                );
                resource.refresh();
              } catch (cause) {
                setError(errorMessage(cause));
              } finally {
                setBusy(false);
              }
            }}
          >
            <div className="form-grid">
              <label>
                Full name
                <input
                  name="name"
                  required
                  maxLength={200}
                  autoComplete="off"
                />
              </label>
              <label>
                Email address
                <input name="email" type="email" required autoComplete="off" />
              </label>
              <label>
                Initial password
                <input
                  name="password"
                  type="password"
                  required
                  minLength={12}
                  maxLength={1024}
                  autoComplete="new-password"
                />
                <span className="field-help">At least 12 characters.</span>
              </label>
              <label>
                Role
                <select aria-label="Role" name="role" defaultValue="requester">
                  {roles.map((role) => (
                    <option key={role}>{role}</option>
                  ))}
                </select>
              </label>
            </div>
            <button className="button" disabled={busy}>
              {busy ? "Creating…" : "Create account"}
            </button>
          </form>
        </Panel>
      )}
      <Panel
        title="Workspace accounts"
        subtitle="Changing a role or disabling an account revokes its active sessions."
      >
        {resource.data ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Role</th>
                  <th>Access</th>
                  <th>Update</th>
                </tr>
              </thead>
              <tbody>
                {resource.data.map((user) => (
                  <AccountRow
                    key={`${user.id}-${user.role}-${user.active}`}
                    user={user}
                    csrf={session!.csrf_token}
                    onSaved={() => {
                      setSuccess("Account access updated.");
                      resource.refresh();
                    }}
                    onError={setError}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : !resource.error ? (
          <Loading />
        ) : null}
      </Panel>
      <div className="role-guide">
        <ShieldCheck size={22} />
        <p>
          <strong>Independent approval is required for everyone.</strong>{" "}
          Requesters submit and track their own work. Reviewers inspect and
          request changes. Approvers authorize or reject. Administrators also
          manage accounts. Even administrators cannot approve their own request.
        </p>
      </div>
    </>
  );
}
function AccountRow({
  user,
  csrf,
  onSaved,
  onError,
}: {
  user: User;
  csrf: string;
  onSaved: () => void;
  onError: (message: string) => void;
}) {
  const [role, setRole] = useState(user.role);
  const [active, setActive] = useState(user.active);
  const [busy, setBusy] = useState(false);
  return (
    <tr>
      <td>
        <strong>{user.name}</strong>
        <span className="cell-meta">{user.email}</span>
      </td>
      <td>
        <select
          aria-label={`Role for ${user.name}`}
          value={role}
          onChange={(event) => setRole(event.target.value as Role)}
          disabled={busy}
        >
          {roles.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </select>
      </td>
      <td>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={active}
            onChange={(event) => setActive(event.target.checked)}
            disabled={busy}
          />
          Active
        </label>
      </td>
      <td>
        <button
          className="button small secondary"
          disabled={busy || (role === user.role && active === user.active)}
          onClick={async () => {
            setBusy(true);
            try {
              await api(
                `/admin/users/${user.id}`,
                { method: "PATCH", body: JSON.stringify({ role, active }) },
                csrf,
              );
              onSaved();
            } catch (cause) {
              onError(errorMessage(cause));
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Saving…" : "Save"}
        </button>
      </td>
    </tr>
  );
}

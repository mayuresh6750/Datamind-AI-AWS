"use client";

import { useState } from "react";
import type { User } from "@/lib/types";

export default function UserRow({
  user,
  currentUserId,
  onRoleChange,
}: {
  user: User;
  currentUserId: string | null;
  onRoleChange: (userId: string, newRole: string) => Promise<void>;
}) {
  const [changing, setChanging] = useState(false);
  // Inline confirmation state — replaces native browser confirm() dialog
  const [confirmPending, setConfirmPending] = useState(false);

  const newRole = user.role === "admin" ? "user" : "admin";
  const label = user.role === "admin" ? "Demote" : "Promote";
  const isSelfDemote = user.user_id === currentUserId && user.role === "admin";
  const actionDisabled = changing || isSelfDemote;

  async function handleConfirm() {
    setConfirmPending(false);
    setChanging(true);
    try {
      await onRoleChange(user.user_id, newRole);
    } finally {
      setChanging(false);
    }
  }

  function handleCancel() {
    setConfirmPending(false);
  }

  return (
    <tr className="border-b">
      <td className="py-2">{user.email}</td>
      <td className="py-2">
        <span
          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
            user.role === "admin"
              ? "bg-blue-100 text-blue-700"
              : "bg-gray-100 text-gray-600"
          }`}
        >
          {user.role}
        </span>
      </td>
      <td className="py-2 text-muted-foreground">{user.active_domain ?? "—"}</td>
      <td className="py-2 text-muted-foreground">
        {new Date(user.created_at).toLocaleDateString()}
      </td>
      <td className="py-2">
        {confirmPending ? (
          /* Inline confirm strip — replaces disruptive browser confirm() */
          <span className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">
              {label} &quot;{user.email}&quot;?
            </span>
            <button
              onClick={handleConfirm}
              className="rounded-md border border-red-300 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
            >
              Yes, {label}
            </button>
            <button
              onClick={handleCancel}
              className="rounded-md border px-2 py-1 text-xs font-medium hover:bg-accent"
            >
              Cancel
            </button>
          </span>
        ) : (
          <button
            onClick={() => !actionDisabled && setConfirmPending(true)}
            disabled={actionDisabled}
            title={
              isSelfDemote
                ? "Admins cannot demote their own account"
                : `${label} this user`
            }
            className="rounded-md border px-2 py-1 text-xs font-medium hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {changing ? "Saving…" : label}
          </button>
        )}
      </td>
    </tr>
  );
}

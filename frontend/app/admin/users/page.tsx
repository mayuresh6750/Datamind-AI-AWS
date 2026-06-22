"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import UserRow from "@/components/admin/UserRow";
import { useAuthStore } from "@/store/authStore";

function extractApiError(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null && "response" in err) {
    const data = (err as { response?: { data?: { detail?: unknown } } }).response
      ?.data;
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.detail === "object" && data.detail !== null)
      return JSON.stringify(data.detail);
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export default function AdminUsersPage() {
  const currentUserId = useAuthStore((state) => state.userId);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    api
      .get<User[]>("/admin/users")
      .then((r) => setUsers(r.data))
      .catch((err: unknown) =>
        setLoadError(extractApiError(err, "Could not load users."))
      )
      .finally(() => setLoading(false));
  }, []);

  async function handleRoleChange(userId: string, newRole: string) {
    setActionError(null);
    try {
      const { data } = await api.patch<{ user_id: string; role: string }>(
        `/admin/users/${userId}/role`,
        null,
        { params: { role: newRole } }
      );
      setUsers((prev) =>
        prev.map((u) => (u.user_id === data.user_id ? { ...u, role: data.role } : u))
      );
    } catch (err: unknown) {
      const message = extractApiError(err, "Could not update the user role.");
      setActionError(message);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Users</h1>

      {loadError && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {loadError}
        </div>
      )}

      {actionError && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {actionError}
        </div>
      )}

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-muted-foreground">
            <th className="text-left py-2">Email</th>
            <th className="text-left py-2">Role</th>
            <th className="text-left py-2">Domain</th>
            <th className="text-left py-2">Created</th>
            <th className="text-left py-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <UserRow
              key={user.user_id}
              user={user}
              currentUserId={currentUserId}
              onRoleChange={handleRoleChange}
            />
          ))}
          {!loading && !loadError && users.length === 0 && (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                No users found.
              </td>
            </tr>
          )}
          {loading && (
            <tr>
              <td colSpan={5} className="py-4 text-center text-muted-foreground">
                Loading…
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

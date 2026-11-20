import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type UserRow = {
  id: string;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  is_active: boolean;
  memberships: { role_name: string; role_code: string }[];
};

type RoleRow = { id: string; code: string; name: string };

export function UsersPage() {
  const qc = useQueryClient();
  const { data: users, error } = useQuery({
    queryKey: ["users"],
    queryFn: () => api<UserRow[]>("/users"),
  });
  const { data: roles } = useQuery({
    queryKey: ["roles"],
    queryFn: () => api<RoleRow[]>("/roles"),
  });

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [roleId, setRoleId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api("/users", {
        method: "POST",
        json: {
          username,
          password,
          first_name: firstName,
          role_id: roleId || null,
        },
      }),
    onSuccess: () => {
      setUsername("");
      setPassword("");
      setFirstName("");
      setFormError(null);
      void qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e: Error) => setFormError(e.message),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-red-700" role="alert">
        {(error as Error).message}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Users</h1>
      <Card>
        <CardHeader>
          <CardTitle>Create user</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid max-w-xl gap-3 md:grid-cols-2" onSubmit={onSubmit}>
            <div>
              <Label htmlFor="new-username">Username</Label>
              <Input
                id="new-username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="new-password">Password</Label>
              <Input
                id="new-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="new-first">First name</Label>
              <Input
                id="new-first"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="new-role">Role</Label>
              <select
                id="new-role"
                className="flex h-10 w-full rounded-md border border-slate-300 px-3 text-sm"
                value={roleId}
                onChange={(e) => setRoleId(e.target.value)}
              >
                <option value="">—</option>
                {(roles || []).map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="md:col-span-2">
              <Button type="submit" disabled={create.isPending}>
                Create
              </Button>
              {formError && <p className="mt-2 text-sm text-red-600">{formError}</p>}
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Directory</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b text-slate-500">
                  <th className="py-2">Username</th>
                  <th>Name</th>
                  <th>Roles</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {(users || []).map((u) => (
                  <tr key={u.id} className="border-b border-slate-100">
                    <td className="py-2 font-medium">{u.username}</td>
                    <td>
                      {u.first_name} {u.last_name}
                    </td>
                    <td>{u.memberships.map((m) => m.role_name).join(", ")}</td>
                    <td>{u.is_active ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

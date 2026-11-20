import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Permission = { id: string; code: string; module: string; description: string };
type Screen = { id: string; code: string; name: string; module: string; route: string };

type Role = {
  id: string;
  code: string;
  name: string;
  permissions: Permission[];
  screens: Screen[];
};

export function RolesPage() {
  const qc = useQueryClient();
  const { data: roles, error } = useQuery({
    queryKey: ["roles"],
    queryFn: () => api<Role[]>("/roles"),
  });
  const { data: permissions } = useQuery({
    queryKey: ["permissions"],
    queryFn: () => api<Permission[]>("/permissions"),
  });
  const { data: screens } = useQuery({
    queryKey: ["screens"],
    queryFn: () => api<Screen[]>("/screens"),
  });

  const [selectedId, setSelectedId] = useState<string>("");
  const selected = (roles || []).find((r) => r.id === selectedId) || (roles || [])[0];
  const [permIds, setPermIds] = useState<string[]>([]);
  const [screenIds, setScreenIds] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  function selectRole(role: Role) {
    setSelectedId(role.id);
    setPermIds(role.permissions.map((p) => p.id));
    setScreenIds(role.screens.map((s) => s.id));
    setMessage(null);
  }

  const savePerms = useMutation({
    mutationFn: () =>
      api(`/roles/${selected!.id}/permissions`, {
        method: "PUT",
        json: { permission_ids: permIds },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["roles"] });
      setMessage("Permissions saved.");
    },
    onError: (e: Error) => setMessage(e.message),
  });

  const saveScreens = useMutation({
    mutationFn: () =>
      api(`/roles/${selected!.id}/screens`, {
        method: "PUT",
        json: { screen_ids: screenIds },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["roles"] });
      setMessage("Screens saved.");
    },
    onError: (e: Error) => setMessage(e.message),
  });

  if (error) {
    return <p className="text-red-600">{(error as Error).message}</p>;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Roles</h1>
      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Role list</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {(roles || []).map((r) => (
              <button
                key={r.id}
                type="button"
                className={`block w-full rounded-md px-3 py-2 text-left text-sm ${
                  selected?.id === r.id ? "bg-brand-50 text-brand-700" : "hover:bg-slate-50"
                }`}
                onClick={() => selectRole(r)}
              >
                {r.name}
              </button>
            ))}
          </CardContent>
        </Card>

        {selected && (
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>
                  Permissions — {selected.name}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {(permissions || []).map((p) => (
                  <label key={p.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={permIds.includes(p.id)}
                      onChange={(e) => {
                        setPermIds((ids) =>
                          e.target.checked ? [...ids, p.id] : ids.filter((x) => x !== p.id),
                        );
                      }}
                    />
                    <span>
                      <code>{p.code}</code> — {p.description}
                    </span>
                  </label>
                ))}
                <Button type="button" onClick={() => savePerms.mutate()}>
                  Save permissions
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Screens — {selected.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {(screens || []).map((s) => (
                  <label key={s.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={screenIds.includes(s.id)}
                      onChange={(e) => {
                        setScreenIds((ids) =>
                          e.target.checked ? [...ids, s.id] : ids.filter((x) => x !== s.id),
                        );
                      }}
                    />
                    <span>
                      {s.name} <span className="text-slate-400">({s.route})</span>
                    </span>
                  </label>
                ))}
                <Button type="button" onClick={() => saveScreens.mutate()}>
                  Save screens
                </Button>
              </CardContent>
            </Card>
            {message && <p className="text-sm text-slate-600">{message}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

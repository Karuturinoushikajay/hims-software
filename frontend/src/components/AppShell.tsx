import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, clearCsrf, type Me } from "@/lib/api";
import { cn } from "@/lib/utils";

type SearchHit = { id: string; full_name: string; uhid: string; mobile: string };

type Props = {
  me: Me;
  onLogout: () => void;
  onFacilityChange: () => void;
};

export function AppShell({ me, onLogout, onFacilityChange }: Props) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const screens = me.screens.length
    ? me.screens
    : [{ id: "home", code: "home", module: "home", name: t("home"), route: "/" }];

  async function handleLogout() {
    await api("/auth/logout", { method: "POST" });
    clearCsrf();
    onLogout();
  }

  async function switchFacility(facilityId: string) {
    await api("/session/facility", { method: "POST", json: { facility_id: facilityId } });
    onFacilityChange();
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
      <aside className="border-r border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-4 py-4">
          <div className="text-lg font-bold text-brand-700">{t("appName")}</div>
          <div className="text-xs text-slate-500">Masters · OPD · Billing · EMR · Pharmacy · Lab · Rad</div>
        </div>
        <nav className="flex flex-col gap-1 p-3" aria-label="Main">
          {screens.map((s) => (
            <NavLink
              key={s.code}
              to={s.route}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-2 text-sm font-medium",
                  isActive ? "bg-brand-50 text-brand-700" : "text-slate-700 hover:bg-slate-50",
                )
              }
            >
              {s.name}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-h-screen flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3">
          <div className="relative min-w-64 flex-1">
            <Input
              aria-label="Find patient"
              placeholder="Name, MR number, mobile, or ABHA"
              value={query}
              autoComplete="off"
              onChange={(e) => {
                const value = e.target.value;
                setQuery(value);
                if (value.trim().length < 2) {
                  setHits([]);
                  return;
                }
                void api<SearchHit[]>(`/patients/search?q=${encodeURIComponent(value)}`)
                  .then(setHits)
                  .catch(() => setHits([]));
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && hits[0]) {
                  navigate(`/consult?patient=${hits[0].id}`);
                  setHits([]);
                  setQuery("");
                }
              }}
            />
            {hits.length > 0 && (
              <ul className="absolute z-10 mt-1 max-h-64 w-full overflow-auto rounded-md border bg-white shadow">
                {hits.map((hit) => (
                  <li key={hit.id}>
                    <button
                      type="button"
                      className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                      onClick={() => {
                        navigate(`/consult?patient=${hit.id}`);
                        setHits([]);
                        setQuery("");
                      }}
                    >
                      {hit.full_name} · {hit.uhid} · {hit.mobile}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-600" htmlFor="facility">
              Facility
            </label>
            <select
              id="facility"
              className="h-9 rounded-md border border-slate-300 px-2 text-sm"
              value={me.active_facility_id || ""}
              onChange={(e) => void switchFacility(e.target.value)}
            >
              {me.memberships.map((m) => (
                <option key={`${m.facility_id}-${m.role_code}`} value={m.facility_id}>
                  {m.facility_name} ({m.role_name})
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-3">
            <select
              aria-label="Language"
              className="h-9 rounded-md border border-slate-300 px-2 text-sm"
              value={i18n.language}
              onChange={(e) => void i18n.changeLanguage(e.target.value)}
            >
              <option value="en">English</option>
              <option value="hi">हिन्दी</option>
              <option value="te">తెలుగు</option>
            </select>
            <span className="text-sm text-slate-600">{me.username}</span>
            <Button variant="outline" size="sm" onClick={() => void handleLogout()}>
              {t("logout")}
            </Button>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

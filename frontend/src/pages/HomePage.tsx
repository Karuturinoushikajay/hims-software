import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Me } from "@/lib/api";

export function HomePage({ me }: { me: Me }) {
  const { t } = useTranslation();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{t("home")}</h1>
      <Card>
        <CardHeader>
          <CardTitle>Welcome, {me.first_name || me.username}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-700">
          <p>
            Roles: <strong>{me.roles.join(", ") || "—"}</strong>
          </p>
          <p>
            2FA:{" "}
            <strong>
              {me.totp_enabled ? "Enabled" : me.pending_2fa_setup ? "Setup required" : "Optional"}
            </strong>
          </p>
          {me.pending_2fa_setup && (
            <p className="rounded-md bg-amber-50 p-3 text-amber-800">
              Your role requires two-factor authentication. Open Settings → enroll TOTP before
              production use. Demo login is allowed until a device is confirmed.
            </p>
          )}
          <p className="text-slate-500">
            Masters are editable under Masters: departments, doctors, services, wards, tariffs, taxes,
            discounts, and templates. Phase 3 billing is live: dues, advances, refunds, credit notes,
            printouts, and day close.
            GST is calculated only after the facility GSTIN is confirmed. Referral commission runs only
            after the TDS rate is confirmed.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

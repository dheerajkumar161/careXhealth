import { useEffect, useState } from "react";
import { Bell, Download, KeyRound, Languages, ShieldCheck, Trash2, UserPlus, UserRound } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, CardHeader, Field, Input, PageHeader, PageSkeleton, Select } from "@/components/ui";
import { api } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { ROLE_LABEL } from "@/lib/constants";
import { setLang, useT } from "@/i18n";
import { LANGUAGE_NAMES } from "@/i18n/strings";
import type { Me } from "@/hooks/useSession";

/** Profile & settings — the same page for every role (doctor, nurse, patient, test center / care partner, admin). */
export default function SettingsPage() {
  const t = useT();
  const { data: me, reload } = useApi<Me>("/api/auth/me");
  const [form, setForm] = useState({ name: "", phone: "", title: "", address: "", emergencyContact: "", organization: "", location: "", language: "en" });
  const [saving, setSaving] = useState(false);
  const [pw, setPw] = useState({ currentPassword: "", newPassword: "", confirm: "" });
  const [changing, setChanging] = useState(false);
  const [notify, setNotify] = useState({ email: true, sms: true });

  useEffect(() => {
    if (!me) return;
    const u = me.user;
    setForm({
      name: u.name,
      phone: u.phone ?? "",
      title: u.title ?? "",
      address: u.address ?? u.patientProfile?.address ?? "",
      emergencyContact: u.patientProfile?.emergencyContact ?? "",
      organization: u.providerProfile?.organization ?? "",
      location: u.providerProfile?.location === "—" ? "" : (u.providerProfile?.location ?? ""),
      language: u.language,
    });
    setNotify({ email: u.notifyEmail !== false, sms: u.notifySms !== false });
  }, [me]);

  if (!me) return <PageSkeleton />;
  const u = me.user;
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const body: Record<string, string | boolean> = { name: form.name, phone: form.phone, title: form.title, address: form.address, language: form.language };
      body.notifyEmail = notify.email;
      body.notifySms = notify.sms;
      if (u.role === "PATIENT") body.emergencyContact = form.emergencyContact;
      if (u.providerProfile) {
        body.organization = form.organization;
        body.location = form.location;
      }
      await api("/api/auth/profile", { method: "PATCH", body });
      setLang(form.language); // the whole app switches language immediately
      toast.success(t("Profile updated"));
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    if (pw.newPassword !== pw.confirm) return toast.error(t("Passwords do not match"));
    setChanging(true);
    try {
      await api("/api/auth/change-password", { body: { currentPassword: pw.currentPassword, newPassword: pw.newPassword } });
      toast.success(t("Password updated"), { description: "Other devices were signed out." });
      setPw({ currentPassword: "", newPassword: "", confirm: "" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not change password");
    } finally {
      setChanging(false);
    }
  }

  return (
    <div>
      <PageHeader title={t("Profile & settings")} subtitle={`${ROLE_LABEL[u.role]} · ${u.email}`} />
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <form onSubmit={save} className="space-y-6">
          <Card>
            <CardHeader title={t("Personal details")} icon={<UserRound className="size-[18px]" />} />
            <div className="grid gap-4 px-5 pb-5 sm:grid-cols-2">
              <Field label={t("Full name")}>
                <Input required minLength={2} value={form.name} onChange={set("name")} />
              </Field>
              <Field label={t("Email")} hint="Your sign-in address cannot be changed here.">
                <Input value={u.email} disabled />
              </Field>
              <Field label={t("Phone")}>
                <Input value={form.phone} onChange={set("phone")} autoComplete="tel" />
              </Field>
              {u.role !== "PATIENT" && (
                <Field label={t("Title")}>
                  <Input value={form.title} onChange={set("title")} />
                </Field>
              )}
              {u.department && (
                <Field label={t("Department")}>
                  <Input value={u.department} disabled />
                </Field>
              )}
              <Field label={t("Address")} className={u.role === "PATIENT" ? "" : "sm:col-span-2"}>
                <Input value={form.address} onChange={set("address")} autoComplete="street-address" />
              </Field>
              {u.role === "PATIENT" && (
                <Field label={t("Emergency contact")} hint="Name, relation and phone number">
                  <Input value={form.emergencyContact} onChange={set("emergencyContact")} />
                </Field>
              )}
              {u.providerProfile && (
                <>
                  <Field label={t("Organization")}>
                    <Input value={form.organization} onChange={set("organization")} />
                  </Field>
                  <Field label={t("Location")}>
                    <Input value={form.location} onChange={set("location")} />
                  </Field>
                </>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title={t("Language")} subtitle={t("Choose the language used for your plan, messages and notifications.")} icon={<Languages className="size-[18px]" />} />
            <div className="px-5 pb-5">
              <Select value={form.language} onChange={set("language")} aria-label={t("Language")} className="max-w-xs">
                {me.languages.map((l) => (
                  <option key={l.code} value={l.code}>
                    {LANGUAGE_NAMES[l.code] ?? l.native} {l.native !== l.name ? `· ${l.name}` : ""}
                  </option>
                ))}
              </Select>
            </div>
          </Card>

          <Card>
            <CardHeader title="Notifications" subtitle="In-app alerts are always on. Choose whether you also receive copies by email or text message (when your hospital has these channels enabled)." icon={<Bell className="size-[18px]" />} />
            <div className="space-y-2 px-5 pb-5 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={notify.email} onChange={(e) => setNotify({ ...notify, email: e.target.checked })} /> Email</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={notify.sms} onChange={(e) => setNotify({ ...notify, sms: e.target.checked })} /> SMS / WhatsApp {!form.phone && <span className="text-xs text-ink-400">(add a phone number above)</span>}</label>
            </div>
          </Card>

          <div className="flex justify-end">
            <Button type="submit" loading={saving}>
              {saving ? t("Saving") : t("Save changes")}
            </Button>
          </div>
        </form>

        <div className="space-y-6">
        {u.role === "PATIENT" && u.patientProfile && <PatientTools patientId={u.patientProfile.id} />}
        <form onSubmit={changePassword}>
          <Card>
            <CardHeader title={t("Change password")} subtitle="Minimum 10 characters with at least one letter and one number." icon={<KeyRound className="size-[18px]" />} />
            <div className="space-y-4 px-5 pb-5">
              <Field label={t("Current password")}>
                <Input type="password" required autoComplete="current-password" value={pw.currentPassword} onChange={(e) => setPw({ ...pw, currentPassword: e.target.value })} />
              </Field>
              <Field label={t("New password")}>
                <Input type="password" required minLength={10} autoComplete="new-password" value={pw.newPassword} onChange={(e) => setPw({ ...pw, newPassword: e.target.value })} />
              </Field>
              <Field label={t("Confirm new password")}>
                <Input type="password" required minLength={10} autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} />
              </Field>
              <p className="flex items-start gap-2 text-[11px] text-ink-500">
                <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-brand-600" /> Changing your password signs you out on every other device.
              </p>
              <Button type="submit" variant="secondary" loading={changing} className="w-full">
                {t("Update password")}
              </Button>
            </div>
          </Card>
        </form>
        </div>
      </div>
    </div>
  );
}

type Caregiver = { id: string; email: string; name?: string | null; status: string };

/** Patient-only: download my record, and invite / remove caregivers who get a read-only view. */
function PatientTools({ patientId }: { patientId: string }) {
  const { data, reload } = useApi<{ caregivers: Caregiver[] }>("/api/caregivers");
  const [email, setEmail] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api<{ link: string }>("/api/caregivers", { body: { email } });
      setLink(window.location.origin + r.link);
      setEmail("");
      reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not create the invite");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card>
        <CardHeader title="My data" subtitle="Download a copy of your record." icon={<Download className="size-[18px]" />} />
        <div className="flex flex-wrap gap-2 px-5 pb-5">
          <a href={`/api/patients/${patientId}/export`}><Button type="button" variant="secondary" size="sm">Download (JSON)</Button></a>
          <a href={`/api/patients/${patientId}/export?format=fhir`}><Button type="button" variant="secondary" size="sm">Download (FHIR)</Button></a>
        </div>
      </Card>
      <Card>
        <CardHeader title="Caregivers" subtitle="Give a family member read-only access to your recovery. You can remove them at any time." icon={<UserPlus className="size-[18px]" />} />
        <div className="space-y-3 px-5 pb-5">
          <form onSubmit={invite} className="flex gap-2">
            <Input type="email" required placeholder="Their email address" value={email} onChange={(e) => setEmail(e.target.value)} />
            <Button type="submit" size="md" loading={busy}>Invite</Button>
          </form>
          {link && (
            <div className="rounded-xl bg-amber-50 p-3 text-xs text-amber-900 ring-1 ring-amber-200">
              Share this one-time link (valid 7 days) — it is shown only once:
              <div className="mt-1 break-all font-mono">{link}</div>
              <button type="button" className="mt-1 font-semibold underline" onClick={() => navigator.clipboard?.writeText(link).then(() => toast.success("Link copied"))}>Copy link</button>
            </div>
          )}
          {data?.caregivers.map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-xl border border-line px-3 py-2 text-sm">
              <span>{c.email} <span className="ml-1 text-xs text-ink-400">{c.status === "ACTIVE" ? "has access" : "invite pending"}</span></span>
              <button type="button" aria-label={`Remove ${c.email}`} className="text-ink-400 hover:text-rose-600" onClick={async () => { await api(`/api/caregivers/${c.id}`, { method: "DELETE" }); reload(); }}><Trash2 className="size-4" /></button>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}

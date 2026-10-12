import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useAppState } from "@/hooks/use-app-state";
import { api, type Settings } from "@/lib/api";

function Toggle({ k, label, hint, value, onSave }: {
  k: keyof Settings; label: string; hint?: string; value: boolean; onSave: (patch: Partial<Settings>) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <Label htmlFor={k} className="font-medium">{label}</Label>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <Switch id={k} checked={value} onCheckedChange={(v) => onSave({ [k]: v })} />
    </div>
  );
}

function Num({ k, label, step = 1, value, onSave }: {
  k: keyof Settings; label: string; step?: number; value: number; onSave: (patch: Partial<Settings>) => void;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={k}>{label}</Label>
      <Input id={k} type="number" step={step} defaultValue={value} onBlur={(e) => onSave({ [k]: Number(e.target.value) })} />
    </div>
  );
}

export default function SettingsPage() {
  const { state, refresh } = useAppState();
  if (!state) return <p className="text-muted-foreground">Loading…</p>;
  const s = state.settings;

  const save = async (patch: Partial<Settings>) => {
    try {
      await api.settings(patch);
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "failed");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Settings</h2>
        <p className="text-sm text-muted-foreground">How cautious applyloop is about submitting on your behalf.</p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Submission</CardTitle></CardHeader>
        <CardContent className="divide-y">
          <Toggle k="dry_run" label="Dry run" hint="Fill forms but never actually submit them." value={s.dry_run} onSave={save} />
          <Toggle k="auto_approve" label="Auto-approve good matches" hint="Submits automatically once every rule below passes." value={s.auto_approve} onSave={save} />
          <Toggle k="allow_drafted" label="Allow drafted essay answers in auto-approve" value={s.allow_drafted} onSave={save} />
          <Toggle k="remote" label="Remote only" value={s.remote} onSave={save} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Thresholds</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Num k="fit_threshold" label="Auto-approve fit threshold" step={0.05} value={s.fit_threshold} onSave={save} />
          <Num k="fit_floor" label="Widen-search fit floor" step={0.05} value={s.fit_floor} onSave={save} />
          <Num k="daily_cap" label="Daily submission cap" value={s.daily_cap} onSave={save} />
          <Num k="daily_target" label="Daily ranking target" value={s.daily_target} onSave={save} />
          <Num k="cooldown_days" label="Days before re-applying to a company" value={s.cooldown_days} onSave={save} />
        </CardContent>
      </Card>
    </div>
  );
}

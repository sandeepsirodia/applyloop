import { AlertTriangle, Pause, Play, Search, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import { StageBadge } from "@/components/shared/StageBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAppState } from "@/hooks/use-app-state";
import { api } from "@/lib/api";

const STAGES = ["ranked", "prepared", "waiting", "approved", "submitted", "dry-run", "needs-check", "failed"];

export default function Pipeline() {
  const { state, refresh } = useAppState();
  if (!state) return <p className="text-muted-foreground">Loading…</p>;
  const s = state.settings;

  const run = (action: string) => async () => {
    try {
      await api.control(action);
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "failed");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Pipeline</h2>
          <p className="text-sm text-muted-foreground">
            {s.state === "running" ? "Running" : "Paused"} · {s.dry_run ? "dry run: nothing is submitted" : s.auto_approve ? "auto-approve on" : "manual approval"}
            {s.kill_switch && (
              <span className="ml-2 inline-flex items-center gap-1 font-medium text-destructive">
                <ShieldAlert className="size-3.5" /> kill switch on
              </span>
            )}
          </p>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" onClick={run("start")} disabled={s.state === "running"}>
            <Play className="size-4" /> Start
          </Button>
          <Button size="sm" variant="outline" onClick={run("pause")} disabled={s.state !== "running"}>
            <Pause className="size-4" /> Pause
          </Button>
          <Button size="sm" variant="outline" onClick={run("discover")}>
            <Search className="size-4" /> Find jobs now
          </Button>
          <Button size="sm" variant={s.kill_switch ? "outline" : "destructive"} onClick={run(s.kill_switch ? "unkill" : "kill")}>
            <AlertTriangle className="size-4" /> {s.kill_switch ? "Release kill switch" : "Kill switch"}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{state.submitted_today}/{s.daily_cap}</div>
            <p className="text-xs text-muted-foreground">submitted today</p>
          </CardContent>
        </Card>
        {STAGES.map((k) => (
          <Card key={k}>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{state.counts[k] || 0}</div>
              <p className="text-xs text-muted-foreground">{k}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Live log</CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-64 rounded-md border bg-muted/30 p-3">
            <div className="space-y-1 font-mono text-xs">
              {state.events.length === 0 && <p className="text-muted-foreground">Nothing yet.</p>}
              {state.events.map((e, i) => (
                <div key={i} className={e.level === "error" ? "text-destructive" : e.level === "warn" ? "text-amber-600 dark:text-amber-400" : ""}>
                  {new Date(e.ts * 1000).toLocaleTimeString()} &nbsp;{e.message}
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Company</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Note</TableHead>
                <TableHead className="text-right">Fit</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {state.recent.map((j) => (
                <TableRow key={j.job_id}>
                  <TableCell className="font-medium">{j.company}</TableCell>
                  <TableCell className="max-w-64 truncate">{j.title}</TableCell>
                  <TableCell><StageBadge stage={j.stage} /></TableCell>
                  <TableCell className="max-w-80 truncate text-sm text-muted-foreground">{j.reason}</TableCell>
                  <TableCell className="text-right">{j.fit != null && <Badge variant="outline">{j.fit.toFixed(2)}</Badge>}</TableCell>
                </TableRow>
              ))}
              {state.recent.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No jobs yet — click "Find jobs now" to rank today's postings.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

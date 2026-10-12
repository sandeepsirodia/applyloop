import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { useAppState } from "@/hooks/use-app-state";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function Budgets() {
  const { state, refresh } = useAppState();
  if (!state) return <p className="text-muted-foreground">Loading…</p>;
  const { budgets } = state;

  const toggle = (site: string, action: "pause" | "resume") => async () => {
    try {
      await api.budget(site, action);
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "failed");
    }
  };

  const sites = Object.entries(budgets.sites);
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Budgets</h2>
        <p className="text-sm text-muted-foreground">Per-site pacing. A paused site waits for you, never gets hammered.</p>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base">Sites</CardTitle></CardHeader>
        <CardContent>
          {budgets.all_paused && (
            <p className="mb-3 rounded-md bg-destructive/10 p-2 text-sm text-destructive">All sites paused: {budgets.all_paused.reason}</p>
          )}
          <Table>
            <TableBody>
              {sites.map(([site, v]) => (
                <TableRow key={site}>
                  <TableCell className="font-medium">{site}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {Object.entries(v.used).map(([k, n]) => `${n}/${v.limits[k] ?? "∞"} ${k.split("_")[1]}`).join(" · ")}
                  </TableCell>
                  <TableCell className={cn("text-sm", (v.paused || v.breaker) && "text-amber-700 dark:text-amber-400")}>
                    {v.paused ? v.paused.reason : v.breaker ? `breaker ${v.breaker.state}` : "ok"}
                  </TableCell>
                  <TableCell className="text-right">
                    {v.paused || v.breaker ? (
                      <Button size="sm" variant="outline" onClick={toggle(site, "resume")}>Resume</Button>
                    ) : (
                      <Button size="sm" variant="outline" onClick={toggle(site, "pause")}>Pause</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {sites.length === 0 && (
                <TableRow><TableCell className="text-muted-foreground">No site visited yet.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

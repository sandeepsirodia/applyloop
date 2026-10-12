import { ExternalLink } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { useAppState } from "@/hooks/use-app-state";
import { api } from "@/lib/api";

export default function Approvals() {
  const { state, refresh } = useAppState();
  if (!state) return <p className="text-muted-foreground">Loading…</p>;

  const act = (fn: (id: string) => Promise<unknown>, id: string) => async () => {
    try {
      await fn(id);
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "failed");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Approvals</h2>
        <p className="text-sm text-muted-foreground">Every answer, where it came from, and the filled form — nothing is sent until you approve it.</p>
      </div>

      {state.approvals.length === 0 && (
        <Card><CardContent className="pt-6 text-muted-foreground">Nothing waiting for approval.</CardContent></Card>
      )}

      {state.approvals.map((j) => (
        <Card key={j.job_id}>
          <CardHeader className="flex-row flex-wrap items-center gap-2 space-y-0">
            <div>
              <CardTitle className="text-base">{j.company} — {j.title}</CardTitle>
            </div>
            <Badge variant="outline">fit {j.fit.toFixed(2)}</Badge>
            <Badge variant="outline">{j.resume_variant}</Badge>
            <div className="ml-auto flex gap-2">
              <Button size="sm" onClick={act(api.approve, j.job_id)}>Approve</Button>
              <Button size="sm" variant="outline" onClick={act(api.reject, j.job_id)}>Reject</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {j.auto.length > 0 && (
              <p className="text-sm text-muted-foreground">Not auto-approved: {j.auto.join("; ")}</p>
            )}
            {j.answers && j.answers.length > 0 && (
              <Table>
                <TableBody>
                  {j.answers.map((a, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium">{a.question}</TableCell>
                      <TableCell>{a.source === "file" ? "📎 " + String(a.value).split("/").pop() : String(a.value)}</TableCell>
                      <TableCell className="text-right text-xs text-muted-foreground">{a.source}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {j.screenshot_url && (
              <img src={j.screenshot_url} alt="the filled form" className="max-w-full rounded-md border" />
            )}
            <a href={j.apply_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-muted-foreground underline underline-offset-2">
              open the posting <ExternalLink className="size-3" />
            </a>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

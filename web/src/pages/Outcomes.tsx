import { useAppState } from "@/hooks/use-app-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function Outcomes() {
  const { state } = useAppState();
  if (!state) return <p className="text-muted-foreground">Loading…</p>;
  const o = state.outcomes;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Outcomes</h2>
        <p className="text-sm text-muted-foreground">When to stop waiting, what's working, what you might lack — from your own replies.</p>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base">{o.applications} applications submitted</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {o.report ? (
            <Button asChild>
              <a href={o.report} target="_blank" rel="noopener noreferrer">Open the latest ghosted report</a>
            </Button>
          ) : (
            <p className="text-sm text-muted-foreground">No report yet. Replies are read on your machine by ghosted — run:</p>
          )}
          <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs">{o.how}</pre>
        </CardContent>
      </Card>
    </div>
  );
}

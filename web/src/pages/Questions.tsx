import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAppState } from "@/hooks/use-app-state";
import { api } from "@/lib/api";

function QuestionCard({ id, question, options, reason, company }: {
  id: number; question: string; options: string[] | null; reason: string; company?: string;
}) {
  const { refresh } = useAppState();
  const [value, setValue] = useState(options ? "" : "");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!value) return;
    setBusy(true);
    try {
      await api.answer(id, value);
      toast.success("Saved — this answer is reused on every form from now on.");
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {question} {company && <span className="font-normal text-muted-foreground">· {company}</span>}
        </CardTitle>
        <p className="text-sm text-muted-foreground">{reason}</p>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {options ? (
          <Select value={value} onValueChange={setValue}>
            <SelectTrigger className="w-64"><SelectValue placeholder="Choose an answer" /></SelectTrigger>
            <SelectContent>
              {options.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
            </SelectContent>
          </Select>
        ) : (
          <Input className="w-64" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Your answer" />
        )}
        <Button onClick={save} disabled={busy || !value}>Save answer</Button>
      </CardContent>
    </Card>
  );
}

export default function Questions() {
  const { state } = useAppState();
  if (!state) return <p className="text-muted-foreground">Loading…</p>;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Questions</h2>
        <p className="text-sm text-muted-foreground">Each question is asked once, then reused on every form automatically.</p>
      </div>
      {state.questions.length === 0 && (
        <Card><CardContent className="pt-6 text-muted-foreground">No questions waiting.</CardContent></Card>
      )}
      {state.questions.map((q) => (
        <QuestionCard key={q.id} id={q.id} question={q.question} options={q.options} reason={q.reason} company={q.job?.company} />
      ))}
    </div>
  );
}

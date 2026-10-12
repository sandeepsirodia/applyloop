import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAppState } from "@/hooks/use-app-state";
import { api, type Question } from "@/lib/api";

const LONG = 140;

function ClampedText({ text, className }: { text: string; className?: string }) {
  const [open, setOpen] = useState(false);
  if (text.length <= LONG) return <span className={className}>{text}</span>;
  return (
    <span className={className}>
      {open ? text : text.slice(0, LONG) + "…"}{" "}
      <button type="button" className="text-xs font-normal text-primary underline underline-offset-2" onClick={() => setOpen((v) => !v)}>
        {open ? "show less" : "show full text"}
      </button>
    </span>
  );
}

function AnswerField({ options, value, onChange }: { options: string[] | null; value: string; onChange: (v: string) => void }) {
  if (options) {
    return (
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-72"><SelectValue placeholder="Choose an answer" /></SelectTrigger>
        <SelectContent>
          {options.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
        </SelectContent>
      </Select>
    );
  }
  return <Textarea className="w-full max-w-md" rows={2} value={value} onChange={(e) => onChange(e.target.value)} placeholder="Your answer" />;
}

function QuestionRow({ question, options, reason, onSave }: {
  question: string; options: string[] | null; reason: string; onSave: (value: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!value) return;
    setBusy(true);
    try {
      await onSave(value);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2 border-b py-3 last:border-b-0">
      <div className="text-sm font-medium"><ClampedText text={question} /></div>
      {reason && <p className="text-xs text-muted-foreground"><ClampedText text={reason} /></p>}
      <div className="flex flex-wrap items-center gap-2">
        <AnswerField options={options} value={value} onChange={setValue} />
        <Button size="sm" onClick={save} disabled={busy || !value}>Save</Button>
      </div>
    </div>
  );
}

export default function Questions() {
  const { state, refresh } = useAppState();
  const [open, setOpen] = useState<Set<string>>(new Set());

  const { shared, byJob, jobCount } = useMemo(() => {
    const questions = state?.questions ?? [];
    const jobCount = new Set(questions.map((q) => `${q.job?.company ?? ""}__${q.job?.title ?? ""}`)).size;
    const byText = new Map<string, Question[]>();
    for (const q of questions) {
      const key = q.question.trim().toLowerCase();
      if (!byText.has(key)) byText.set(key, []);
      byText.get(key)!.push(q);
    }
    const shared = [...byText.values()].filter((g) => g.length > 1);
    const sharedIds = new Set(shared.flatMap((g) => g.map((q) => q.id)));

    const byJob = new Map<string, { company?: string; title?: string; questions: Question[] }>();
    for (const q of questions) {
      if (sharedIds.has(q.id)) continue;
      const key = `${q.job?.company ?? ""}__${q.job?.title ?? ""}`;
      if (!byJob.has(key)) byJob.set(key, { company: q.job?.company, title: q.job?.title, questions: [] });
      byJob.get(key)!.questions.push(q);
    }
    return { shared, byJob, jobCount };
  }, [state?.questions]);

  if (!state) return <p className="text-muted-foreground">Loading…</p>;

  const toggle = (key: string) => setOpen((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const answerAll = async (ids: number[], value: string) => {
    try {
      await Promise.all(ids.map((id) => api.answer(id, value)));
      toast.success(ids.length > 1 ? `Saved — applied to ${ids.length} applications at once.` : "Saved — reused on every form from now on.");
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "failed");
    }
  };

  const total = state.questions.length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Questions</h2>
        <p className="text-sm text-muted-foreground">
          {total === 0 ? "Nothing waiting on you." : `${total} question(s) across ${jobCount} job(s) — ${shared.length} can be answered once for everyone. Each is asked once, then reused automatically.`}
        </p>
      </div>

      {total === 0 && (
        <Card><CardContent className="pt-6 text-muted-foreground">No questions waiting.</CardContent></Card>
      )}

      {shared.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Answer once, applies everywhere</CardTitle>
            <p className="text-sm text-muted-foreground">The same question showed up on more than one application — answer it a single time.</p>
          </CardHeader>
          <CardContent className="divide-y">
            {shared.map((group) => {
              const q = group[0];
              const companies = [...new Set(group.map((g) => g.job?.company).filter(Boolean))] as string[];
              return (
                <div key={q.question} className="space-y-2 py-3 first:pt-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {companies.map((c) => <Badge key={c} variant="secondary">{c}</Badge>)}
                  </div>
                  <QuestionRow
                    question={q.question}
                    options={q.options}
                    reason={group.length > 1 ? `Asked on ${group.length} applications` : q.reason}
                    onSave={(value) => answerAll(group.map((g) => g.id), value)}
                  />
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {[...byJob.entries()].map(([key, job]) => {
        const isOpen = open.has(key);
        return (
          <Card key={key}>
            <button type="button" className="flex w-full items-center justify-between px-6 py-4 text-left" onClick={() => toggle(key)}>
              <div>
                <div className="font-medium">{job.company || "Unknown company"}</div>
                <div className="text-sm text-muted-foreground">{job.title}</div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline">{job.questions.length} question{job.questions.length === 1 ? "" : "s"}</Badge>
                {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
              </div>
            </button>
            {isOpen && (
              <CardContent className="divide-y border-t pt-3">
                {job.questions.map((q) => (
                  <QuestionRow key={q.id} question={q.question} options={q.options} reason={q.reason} onSave={(value) => answerAll([q.id], value)} />
                ))}
              </CardContent>
            )}
          </Card>
        );
      })}
    </div>
  );
}

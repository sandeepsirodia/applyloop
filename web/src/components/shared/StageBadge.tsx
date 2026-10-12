import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const COLORS: Record<string, string> = {
  submitted: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  prepared: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  ranked: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  waiting: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  "dry-run": "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  "needs-check": "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  rejected: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  submitting: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
};

export function StageBadge({ stage }: { stage: string }) {
  return <Badge variant="outline" className={cn("border-0 font-normal", COLORS[stage])}>{stage}</Badge>;
}

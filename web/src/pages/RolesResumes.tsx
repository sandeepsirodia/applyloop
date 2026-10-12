import { Upload, X } from "lucide-react";
import { type ChangeEvent, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { useAppState } from "@/hooks/use-app-state";
import { api, fileToBase64 } from "@/lib/api";

export default function RolesResumes() {
  const { state, refresh } = useAppState();
  const [newRole, setNewRole] = useState("");
  const [label, setLabel] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  if (!state) return <p className="text-muted-foreground">Loading…</p>;
  const s = state.settings;

  const addRole = async () => {
    if (!newRole.trim()) return;
    await api.addRole(newRole.trim());
    setNewRole("");
    await refresh();
  };
  const removeRole = async (r: string) => {
    await api.removeRole(r);
    await refresh();
  };
  const acceptAdjacent = async (family: string) => {
    await api.settings({ adjacent_accepted: [...s.adjacent_accepted, family] });
    await refresh();
  };

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const data = await fileToBase64(file);
      const res = await api.uploadResume(label || file.name.replace(/\.\w+$/, ""), file.name, data);
      toast(
        res.findings.length
          ? `What a parser loses from this resume: ${res.findings.map((f) => f.message).join("; ")}`
          : "No parsing problems found in this resume.",
      );
      setLabel("");
      if (fileRef.current) fileRef.current.value = "";
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "upload failed");
    } finally {
      setUploading(false);
    }
  };

  const markReviewed = async (lbl: string) => {
    await api.markReviewed(lbl);
    await refresh();
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Roles & resumes</h2>
        <p className="text-sm text-muted-foreground">What you're looking for, and what gets sent.</p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Roles</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {s.roles.length === 0 && <p className="text-sm text-muted-foreground">No roles yet.</p>}
            {s.roles.map((r) => (
              <Badge key={r} variant="secondary" className="gap-1 pr-1">
                {r}
                <button onClick={() => removeRole(r)} className="rounded-full p-0.5 hover:bg-background/60" aria-label={`remove ${r}`}>
                  <X className="size-3" />
                </button>
              </Badge>
            ))}
          </div>
          <div className="flex gap-2">
            <Input value={newRole} onChange={(e) => setNewRole(e.target.value)} placeholder="e.g. backend engineer" onKeyDown={(e) => e.key === "Enter" && addRole()} />
            <Button onClick={addRole}>Add role</Button>
          </div>
          {s.adjacent_suggested && s.adjacent_suggested.length > 0 && (
            <div className="rounded-md border bg-muted/40 p-3 text-sm">
              <p className="mb-2 font-medium">Roles you didn't list that fit your skills:</p>
              <div className="flex flex-wrap gap-2">
                {s.adjacent_suggested.map((a) => (
                  <Button key={a.family} size="sm" variant="outline" onClick={() => acceptAdjacent(a.family)}>
                    + {a.family} ({Math.round(a.median_cover * 100)}% skill cover, {a.open} open)
                  </Button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Resumes</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <Table>
            <TableBody>
              {Object.entries(s.resumes).map(([lbl, r]) => (
                <TableRow key={lbl}>
                  <TableCell className="align-top font-medium">
                    {lbl}
                    {lbl === s.default_resume && <span className="ml-1 text-xs text-muted-foreground">(default)</span>}
                  </TableCell>
                  <TableCell className="align-top">
                    {r.findings.length > 0 ? (
                      <ul className="space-y-1 text-sm text-amber-700 dark:text-amber-400">
                        {r.findings.map((f, i) => <li key={i}>{f.message}</li>)}
                      </ul>
                    ) : (
                      <span className="text-sm text-muted-foreground">no parsing problems</span>
                    )}
                  </TableCell>
                  <TableCell className="align-top text-right">
                    {r.reviewed ? (
                      <Badge variant="outline">reviewed ✓</Badge>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => markReviewed(lbl)}>Mark reviewed</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {Object.keys(s.resumes).length === 0 && (
                <TableRow><TableCell className="text-muted-foreground">No resume yet.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
          <div className="flex flex-wrap items-center gap-2 border-t pt-4">
            <Input className="w-48" placeholder="label, e.g. backend-v2" value={label} onChange={(e) => setLabel(e.target.value)} />
            <Input ref={fileRef} type="file" accept=".pdf,.docx,.md,.txt,.json" className="w-64" onChange={upload} disabled={uploading} />
            <span className="flex items-center gap-1 text-sm text-muted-foreground">
              <Upload className="size-4" /> {uploading ? "Parsing…" : "Pick a file to add it"}
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

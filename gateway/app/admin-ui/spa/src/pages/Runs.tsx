import React from "react";
import { useMsal } from "@azure/msal-react";
import {
  Title3, Text, Dropdown, Option, Button, Spinner, Badge, tokens,
  Table, TableHeader, TableRow, TableHeaderCell, TableBody, TableCell,
  MessageBar, MessageBarBody,
} from "@fluentui/react-components";
import { RuntimeConfig, apiScopes } from "../auth";
import { apiFetch } from "../api";

interface RunHalt { time?: string; reason: string }
interface RunDowngrade { effectiveModel?: string; downgradeLevel?: string }
interface RunRow {
  runId: string;
  lastSeen?: string;
  callCount: number;
  steps: number;
  agents: string[];
  costUsd: number;
  halts: RunHalt[];
  downgrades: RunDowngrade[];
}
interface RunsData { items: RunRow[] }

const RANGES = ["1h", "24h", "7d"];

function fmtTime(t?: string): string {
  if (!t) return "—";
  const d = new Date(t);
  return Number.isNaN(d.getTime()) ? t : d.toLocaleString();
}

function fmtUsd(v: number): string {
  if (!v) return "$0.00";
  return v >= 0.01 ? `$${v.toFixed(2)}` : `$${v.toFixed(4)}`;
}

export default function Runs({ config }: { config: RuntimeConfig }) {
  const { instance } = useMsal();
  const scopes = React.useMemo(() => apiScopes(config), [config]);
  const [range, setRange] = React.useState("24h");
  const [data, setData] = React.useState<RunsData | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    setLoading(true); setErr(null);
    apiFetch(instance, scopes, `/api/runs?range=${range}`)
      .then(async (r) => {
        if (!r.ok) { setErr(`Load failed: ${r.status}`); return; }
        setData(await r.json());
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [instance, scopes, range]);

  React.useEffect(() => { load(); }, [load]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 1100 }}>
      <Title3>Runs</Title3>
      <Text>Recent TokenOps runs by run id, with their last-seen activity, estimated cost, halts, and downgrade events.</Text>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Dropdown value={range} selectedOptions={[range]}
                  onOptionSelect={(_, d) => d.optionValue && setRange(d.optionValue)} style={{ minWidth: 100 }}>
          {RANGES.map((r) => <Option key={r} value={r}>{r}</Option>)}
        </Dropdown>
        <Button onClick={load} disabled={loading}>Refresh</Button>
      </div>
      {err && <MessageBar intent="error"><MessageBarBody>{err}</MessageBarBody></MessageBar>}
      {loading ? <Spinner label="Loading…" /> : data && (
        <Table aria-label="Recent runs">
          <TableHeader><TableRow>
            <TableHeaderCell>Run</TableHeaderCell>
            <TableHeaderCell>Last seen</TableHeaderCell>
            <TableHeaderCell>Agents</TableHeaderCell>
            <TableHeaderCell>Calls / steps</TableHeaderCell>
            <TableHeaderCell>Cost</TableHeaderCell>
            <TableHeaderCell>Halts</TableHeaderCell>
            <TableHeaderCell>Downgrades</TableHeaderCell>
          </TableRow></TableHeader>
          <TableBody>
            {data.items.length === 0
              ? <TableRow><TableCell colSpan={7}><Text style={{ color: tokens.colorNeutralForeground3 }}>No run telemetry in this period yet.</Text></TableCell></TableRow>
              : data.items.map((run) => (
                <TableRow key={run.runId}>
                  <TableCell><Text style={{ fontFamily: "monospace" }}>{run.runId}</Text></TableCell>
                  <TableCell>{fmtTime(run.lastSeen)}</TableCell>
                  <TableCell>{run.agents.length ? run.agents.join(", ") : "—"}</TableCell>
                  <TableCell>{`${run.callCount} / ${run.steps}`}</TableCell>
                  <TableCell>{fmtUsd(run.costUsd)}</TableCell>
                  <TableCell>
                    {run.halts.length
                      ? <Badge appearance="tint" color="danger">{run.halts[run.halts.length - 1].reason}</Badge>
                      : "—"}
                  </TableCell>
                  <TableCell>
                    {run.downgrades.length
                      ? <Badge appearance="tint" color="warning">
                          {run.downgrades[run.downgrades.length - 1].effectiveModel || run.downgrades.length}
                        </Badge>
                      : "—"}
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

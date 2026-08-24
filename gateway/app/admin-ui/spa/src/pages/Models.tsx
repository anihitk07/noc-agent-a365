import React from "react";
import { useMsal } from "@azure/msal-react";
import {
  Title3, Text, Checkbox, Button, Spinner, Badge, MessageBar, MessageBarBody,
  Input, Label, Table, TableBody, TableCell, TableHeader, TableHeaderCell, TableRow,
} from "@fluentui/react-components";
import { RuntimeConfig, apiScopes } from "../auth";
import { apiFetch } from "../api";
import { modelsByPrice } from "../modelLabel";
import ConsumerPicker from "../components/ConsumerPicker";

type Intent = "success" | "error";
interface Price { prompt: number; completion: number }
interface PricingDoc {
  region: string;
  models: Record<string, Price>;
  overrides: Record<string, Price>;
  sourceModels: Record<string, Price>;
  refreshed_at?: string;
}
interface DiffRow { model: string; current?: Price | null; next?: Price | null }
interface PreviewDoc extends PricingDoc { diff: DiffRow[] }

function perMillion(v?: number): string {
  if (v == null) return "—";
  return `$${(v * 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function sortModels(ids: string[], prices: Record<string, Price> | undefined): string[] {
  const rank = (id: string): [number, number] => {
    const p = prices?.[id];
    return p ? [p.completion, p.prompt] : [-1, -1];
  };
  return ids.slice().sort((a, b) => {
    const [ac, ap] = rank(a);
    const [bc, bp] = rank(b);
    if (bc !== ac) return bc - ac;
    if (bp !== ap) return bp - ap;
    return a.localeCompare(b);
  });
}

export default function Models({ config }: { config: RuntimeConfig }) {
  const { instance } = useMsal();
  const scopes = React.useMemo(() => apiScopes(config), [config]);
  const [consumer, setConsumer] = React.useState<string | null>(null);
  const [models, setModels] = React.useState<string[]>([]);
  const [isDefault, setIsDefault] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [pricingBusy, setPricingBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<{ intent: Intent; text: string } | null>(null);
  const [pricingMsg, setPricingMsg] = React.useState<{ intent: Intent; text: string } | null>(null);
  const [pricing, setPricing] = React.useState<PricingDoc | null>(null);
  const [preview, setPreview] = React.useState<PreviewDoc | null>(null);
  const [region, setRegion] = React.useState("eastus2");
  const [overrides, setOverrides] = React.useState<Record<string, { prompt: string; completion: string }>>({});

  const aliases = React.useMemo(() => {
    const ids = Array.from(new Set([...Object.keys(config.aliasModels ?? {}), ...Object.keys(pricing?.models ?? {}), ...Object.keys(pricing?.overrides ?? {})]));
    return sortModels(ids.length ? ids : modelsByPrice(config), pricing?.models ?? config.modelPrices);
  }, [config, pricing]);

  const loadPricing = React.useCallback(async () => {
    const r = await apiFetch(instance, scopes, "/api/pricing");
    if (!r.ok) throw new Error(`Pricing load failed: ${r.status}`);
    const body: PricingDoc = await r.json();
    setPricing(body);
    setRegion(body.region || "eastus2");
    const nextOverrides: Record<string, { prompt: string; completion: string }> = {};
    Object.entries(body.overrides ?? {}).forEach(([model, rate]) => {
      nextOverrides[model] = { prompt: String(rate.prompt), completion: String(rate.completion) };
    });
    setOverrides(nextOverrides);
  }, [instance, scopes]);

  React.useEffect(() => {
    loadPricing().catch((e) => setPricingMsg({ intent: "error", text: e instanceof Error ? e.message : String(e) }));
  }, [loadPricing]);

  React.useEffect(() => {
    if (!consumer) return;
    setLoading(true); setMsg(null);
    setModels([]); setIsDefault(false);
    apiFetch(instance, scopes, `/api/consumers/${consumer}/config`)
      .then(async (r) => {
        if (!r.ok) { setMsg({ intent: "error", text: `Load failed: ${r.status}` }); return; }
        const b = await r.json();
        setModels(b.allowed_models ?? []);
        setIsDefault(b.isDefault);
      })
      .catch((e) => setMsg({ intent: "error", text: String(e) }))
      .finally(() => setLoading(false));
  }, [consumer, instance, scopes]);

  function toggle(alias: string, checked: boolean) {
    setModels((m) => (checked ? [...new Set([...m, alias])] : m.filter((x) => x !== alias)));
  }

  function setOverride(model: string, field: "prompt" | "completion", value: string) {
    setOverrides((current) => ({
      ...current,
      [model]: { prompt: current[model]?.prompt ?? "", completion: current[model]?.completion ?? "", [field]: value },
    }));
  }

  function overridePayload() {
    const out: Record<string, { prompt?: number; completion?: number }> = {};
    Object.entries(overrides).forEach(([model, rate]) => {
      const prompt = rate.prompt.trim();
      const completion = rate.completion.trim();
      if (!prompt && !completion) return;
      out[model] = {
        ...(prompt ? { prompt: Number(prompt) } : {}),
        ...(completion ? { completion: Number(completion) } : {}),
      };
    });
    return out;
  }

  async function save() {
    if (!consumer || busy) return;
    setBusy(true); setMsg(null);
    try {
      const r = await apiFetch(instance, scopes, `/api/consumers/${consumer}/config`, {
        method: "PUT", body: JSON.stringify({ allowed_models: models }),
      });
      if (!r.ok) { setMsg({ intent: "error", text: `Save failed: ${r.status}` }); return; }
      setIsDefault(false);
      setMsg({ intent: "success", text: `Saved allowed models for consumer ${consumer}.` });
    } catch (e) {
      setMsg({ intent: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function previewPricing() {
    setPricingBusy(true); setPricingMsg(null);
    try {
      const r = await apiFetch(instance, scopes, "/api/pricing/preview", {
        method: "POST",
        body: JSON.stringify({ region, overrides: overridePayload() }),
      });
      if (!r.ok) { setPricingMsg({ intent: "error", text: `Preview failed: ${r.status}` }); return; }
      const body: PreviewDoc = await r.json();
      setPreview(body);
      setPricingMsg({ intent: "success", text: `Fetched latest Retail Prices API rates for ${body.region}. Review the diff below, then apply.` });
    } catch (e) {
      setPricingMsg({ intent: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setPricingBusy(false);
    }
  }

  async function applyRefresh() {
    setPricingBusy(true); setPricingMsg(null);
    try {
      const r = await apiFetch(instance, scopes, "/api/pricing/refresh", {
        method: "POST",
        body: JSON.stringify({ region, overrides: overridePayload() }),
      });
      if (!r.ok) { setPricingMsg({ intent: "error", text: `Refresh failed: ${r.status}` }); return; }
      await loadPricing();
      setPreview(null);
      setPricingMsg({ intent: "success", text: "Saved refreshed model prices to Cosmos." });
    } catch (e) {
      setPricingMsg({ intent: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setPricingBusy(false);
    }
  }

  async function saveOverrides() {
    setPricingBusy(true); setPricingMsg(null);
    try {
      const r = await apiFetch(instance, scopes, "/api/pricing", {
        method: "PUT",
        body: JSON.stringify({ region, overrides: overridePayload() }),
      });
      if (!r.ok) { setPricingMsg({ intent: "error", text: `Override save failed: ${r.status}` }); return; }
      await loadPricing();
      setPreview(null);
      setPricingMsg({ intent: "success", text: "Saved manual price overrides." });
    } catch (e) {
      setPricingMsg({ intent: "error", text: e instanceof Error ? e.message : String(e) });
    } finally {
      setPricingBusy(false);
    }
  }

  function describeModel(id: string) {
    const label = config.aliasModels?.[id];
    const price = pricing?.models?.[id] ?? config.modelPrices?.[id];
    const parts: string[] = [];
    if (label && label !== id) parts.push(label);
    if (price) parts.push(`in ${perMillion(price.prompt)} / out ${perMillion(price.completion)} per 1M`);
    return parts.length ? `${id} (${parts.join(" · ")})` : id;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 900 }}>
      <Title3>Models — allowed models per consumer</Title3>
      <Text>Select the models this consumer may call. Requests for any other model are rejected by the gateway with 403.</Text>
      <ConsumerPicker config={config} selected={consumer} onSelect={setConsumer} />
      {consumer && (loading ? <Spinner label="Loading…" /> : (
        <>
          {isDefault && <Badge appearance="tint" color="informative">Inheriting global default (no per-consumer config yet)</Badge>}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {aliases.map((a) => (
              <Checkbox key={a} label={describeModel(a)}
                        checked={models.includes(a)}
                        onChange={(_, d) => toggle(a, !!d.checked)} />
            ))}
          </div>
          <Button appearance="primary" disabled={busy} onClick={save} style={{ alignSelf: "flex-start" }}>Save</Button>
        </>
      ))}
      {msg && <MessageBar intent={msg.intent}><MessageBarBody>{msg.text}</MessageBarBody></MessageBar>}

      <Title3>Model pricing</Title3>
      <Text>Refresh Azure Retail Prices API rates for Foundry/OpenAI models, then pin any manual overrides if Finance needs a specific rate.</Text>
      <div style={{ display: "flex", gap: 12, alignItems: "end", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <Label htmlFor="pricing-region">Region</Label>
          <Input id="pricing-region" value={region} onChange={(_, d) => setRegion(d.value)} />
        </div>
        <Button onClick={previewPricing} disabled={pricingBusy}>Refresh from Retail Prices API</Button>
        <Button appearance="secondary" onClick={saveOverrides} disabled={pricingBusy}>Save overrides only</Button>
        {preview && <Button appearance="primary" onClick={applyRefresh} disabled={pricingBusy}>Apply refresh</Button>}
      </div>
      {pricingBusy && <Spinner label="Working…" />}
      {pricingMsg && <MessageBar intent={pricingMsg.intent}><MessageBarBody>{pricingMsg.text}</MessageBarBody></MessageBar>}
      <Table aria-label="Model pricing">
        <TableHeader>
          <TableRow>
            <TableHeaderCell>Model</TableHeaderCell>
            <TableHeaderCell>Current prompt / 1M</TableHeaderCell>
            <TableHeaderCell>Current completion / 1M</TableHeaderCell>
            <TableHeaderCell>Override prompt / 1K</TableHeaderCell>
            <TableHeaderCell>Override completion / 1K</TableHeaderCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {aliases.map((model) => {
            const current = pricing?.models?.[model] ?? config.modelPrices?.[model];
            return (
              <TableRow key={model}>
                <TableCell>{describeModel(model)}</TableCell>
                <TableCell>{perMillion(current?.prompt)}</TableCell>
                <TableCell>{perMillion(current?.completion)}</TableCell>
                <TableCell>
                  <Input value={overrides[model]?.prompt ?? ""} onChange={(_, d) => setOverride(model, "prompt", d.value)} placeholder="optional per-1K USD" />
                </TableCell>
                <TableCell>
                  <Input value={overrides[model]?.completion ?? ""} onChange={(_, d) => setOverride(model, "completion", d.value)} placeholder="optional per-1K USD" />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {preview && (
        <>
          <Title3>Refresh diff</Title3>
          {preview.diff.length === 0 ? <Text>No pricing changes detected.</Text> : (
            <Table aria-label="Pricing diff">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>Model</TableHeaderCell>
                  <TableHeaderCell>Current prompt / 1M</TableHeaderCell>
                  <TableHeaderCell>Current completion / 1M</TableHeaderCell>
                  <TableHeaderCell>Next prompt / 1M</TableHeaderCell>
                  <TableHeaderCell>Next completion / 1M</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.diff.map((row) => (
                  <TableRow key={row.model}>
                    <TableCell>{row.model}</TableCell>
                    <TableCell>{perMillion(row.current?.prompt ?? undefined)}</TableCell>
                    <TableCell>{perMillion(row.current?.completion ?? undefined)}</TableCell>
                    <TableCell>{perMillion(row.next?.prompt ?? undefined)}</TableCell>
                    <TableCell>{perMillion(row.next?.completion ?? undefined)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </div>
  );
}

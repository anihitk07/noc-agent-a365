# Guide: Alert Storm Triage — Identifying Root Cause in High-Volume Alert Events

## Summary
An alert storm occurs when a single fault triggers a cascade of downstream alarms across multiple network layers (physical → logical → service). In large networks, a single fibre cut can produce 2,000+ alerts within 90 seconds. The purpose of this guide is to cut through the noise and identify the root cause.

## Indicators of an Alert Storm
- Alert rate exceeds **50 alerts/minute** sustained for > 2 minutes
- Alerts span **3+ network layers** (transport, routing, service)
- Alerts share a **topological corridor** (e.g., all SYD-MEL related)
- Multiple alert types present simultaneously: `LINK_DOWN`, `BGP_PEER_LOSS`, `OSPF_ADJACENCY_DOWN`, `HIGH_CPU`, `SERVICE_DEGRADATION`

## Triage Procedure

### Step 1: Temporal Clustering
- Sort all alerts by timestamp
- Identify the **earliest alert** — this is the most likely root cause
- Group alerts into time windows: T+0s, T+5s, T+15s, T+30s, T+60s, T+90s
- The earliest window typically contains the root cause; later windows contain symptoms

### Step 2: Topological Correlation
- Query the ontology graph to find the **common upstream ancestor** of all alert sources
- Traverse `CONNECTS_TO`, `AGGREGATES_TO`, `ROUTES_VIA` relationships in reverse (upstream) direction
- The entity instance that is the common ancestor of the most alert sources is the probable root cause
- Example: If all 2,000 alert sources trace upstream to `LINK-SYD-MEL-FIBRE-01`, that link is the root cause

### Step 3: Alert Type Hierarchy
Alert types have a natural cause-effect ordering. Use this to confirm the root cause:

```
LINK_DOWN (physical)
  └── causes → BGP_PEER_LOSS (routing)
       └── causes → OSPF_ADJACENCY_DOWN (routing)
            └── causes → ROUTE_WITHDRAWAL (routing)
                 └── causes → HIGH_CPU (device)
                      └── causes → PACKET_LOSS_THRESHOLD (transport)
                           └── causes → SERVICE_DEGRADATION (service)
                                └── causes → DUPLICATE_ALERT (noise)
```

If your earliest alert is `LINK_DOWN`, everything downstream is a symptom.

### Step 4: Suppress Symptoms
- Once root cause is confirmed, **suppress all downstream alerts** as symptoms
- This reduces the 2,000 alert wall to 1 actionable root cause
- Tag suppressed alerts with the root cause ticket ID for audit trail

### Step 5: Impact Assessment
- Use the root cause entity as the starting point
- Query ontology: traverse `ROUTES_VIA`, `DEPENDS_ON_MPLSPATH` / `DEPENDS_ON_AGGSWITCH` / `DEPENDS_ON_BASESTATION` relationships to find impacted services
- Check `SLAPolicy` entities for penalty exposure
- Prioritize: Enterprise SLA > Broadband > Mobile

## Anti-Patterns to Avoid
- **Don't treat each alert independently** — this creates duplicate tickets and wasted effort
- **Don't start with service alarms** — these are symptoms, not causes
- **Don't rely on severity alone** — a CRITICAL service alarm is a symptom if there's an underlying LINK_DOWN

## Related Runbooks
- `fibre_cut_runbook.md`
- `bgp_peer_loss_runbook.md`
- `traffic_engineering_reroute.md`

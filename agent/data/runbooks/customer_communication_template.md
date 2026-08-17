# Template: Customer Communication — SLA Breach Notification

## Summary
When a network incident impacts enterprise customers with SLA agreements, proactive communication is required. This template provides standard formats for different stages of incident lifecycle.

---

## Template 1: Initial Notification (within 15 minutes of impact detection)

**Subject**: [P1] Service Impact Notification — {ServiceName} — {IncidentId}

**Body**:

Dear {CustomerName} Operations Team,

We are writing to notify you of a service-affecting event impacting your {ServiceType} service ({ServiceId}).

**Incident Details:**
- **Incident ID**: {IncidentId}
- **Start Time**: {IncidentStartTime} (UTC)
- **Affected Service**: {ServiceName} ({ServiceId})
- **Current Impact**: {ImpactDescription}
- **Severity**: {SeverityLevel}

**What we know:**
{RootCauseSummary}

**What we are doing:**
Our automated network operations system has detected the issue, identified the root cause, and initiated corrective action. {ActionSummary}

**Next update**: We will provide an update within 30 minutes or sooner if there is a material change.

**Escalation contact**: NOC — noc@telco.example.com | +61-2-XXXX-XXXX

---

## Template 2: Update Notification (every 30 minutes during active incident)

**Subject**: [UPDATE] {ServiceName} — {IncidentId} — {UpdateNumber}

**Body**:

Dear {CustomerName} Operations Team,

This is update #{UpdateNumber} for incident {IncidentId}.

**Current Status**: {CurrentStatus}
**Elapsed Time**: {ElapsedTime}

**Progress since last update:**
{ProgressSummary}

**Estimated time to resolution**: {ETR}

**SLA Status:**
- Availability SLA: {AvailabilityPct}% target | Current downtime: {DowntimeMinutes} minutes
- Latency SLA: {MaxLatencyMs}ms target | Current: {CurrentLatencyMs}ms

---

## Template 3: Resolution Notification

**Subject**: [RESOLVED] {ServiceName} — {IncidentId}

**Body**:

Dear {CustomerName} Operations Team,

We are pleased to confirm that incident {IncidentId} has been resolved.

**Resolution Summary:**
- **Incident ID**: {IncidentId}
- **Start Time**: {IncidentStartTime} (UTC)
- **Resolution Time**: {ResolutionTime} (UTC)
- **Total Duration**: {TotalDuration}
- **Root Cause**: {RootCause}
- **Resolution Action**: {ResolutionAction}

**SLA Impact Assessment:**
- Total downtime: {TotalDowntimeMinutes} minutes
- SLA threshold: {AvailabilityPct}% ({AllowedDowntimeMinutes} minutes/month)
- SLA status: {SLAStatus}

**Preventive measures:**
{PreventiveMeasures}

A formal Root Cause Analysis (RCA) report will be provided within 5 business days.

---

---

## Persona Templates (multi-audience incident lifecycle broadcast)

Templates 1–3 above are the **customer-facing** voice. The four templates
below are the **internal/partner-facing** voices used by
`agent/notifications.py`'s `broadcast_incident_update()` — one send per
persona per lifecycle stage (`detection` | `escalation` | `mitigation` |
`resolution`), each with its own framing and level of technical detail.
All use the same single-brace `{Variable}` substitution as Templates 1–3.

### Persona: executives

**Subject**: [{LifecycleStage}] {ServiceName} incident — business impact summary

**Body**:

{CustomerFacingImpactCount} customer(s)/service(s) affected. Current status:
{CurrentStatus}. Business impact: {BusinessImpactSummary}. ETR:
{ETR}. Full technical detail is not included in this summary — see the NOC
channel for the live incident thread.

### Persona: technical

**Subject**: [{LifecycleStage}] {ServiceName} — {IncidentId} — technical detail

**Body**:

{RootCauseSummary}

Telemetry: {TelemetrySummary}
Remediation steps taken/in progress: {ActionSummary}
Runbook reference: {RunbookReference}

### Persona: venue

**Subject**: [{LifecycleStage}] Service notice — {VenueName}

**Body**:

This notice is scoped to {VenueName} only. {VenueImpactDescription}.
Estimated resolution: {ETR}. Contact NOC at noc@telco.example.com with
questions specific to this site.

### Persona: partners

**Subject**: [{LifecycleStage}] {ServiceName} — SLA/contractual notice — {IncidentId}

**Body**:

Per our service agreement, this is a {LifecycleStage} notice for
{ServiceId}. SLA status: {SLAStatus}. No internal telemetry or root-cause
detail is included per the partner-tier restricted content policy — see
`agent/notifications.py`'s `PERSONAS["partners"]` field allow-list.

---

## Variable Reference

| Variable | Source | Example |
|---|---|---|
| {ServiceName} | Service entity — ServiceName property | ACME Corp Enterprise VPN |
| {ServiceId} | Service entity — ServiceId key | VPN-ACME-CORP |
| {CustomerName} | Service entity — CustomerName property | ACME Corporation |
| {ServiceType} | Service entity — ServiceType property | EnterpriseVPN |
| {IncidentId} | Ticketing system | INC-2026-02-06-0001 |
| {SeverityLevel} | Alert severity mapping | P1 — Critical |
| {RootCause} | Troubleshooting agent output | Physical fibre cut on LINK-SYD-MEL-FIBRE-01 |
| {AvailabilityPct} | SLAPolicy entity — AvailabilityPct | 99.99 |
| {MaxLatencyMs} | SLAPolicy entity — MaxLatencyMs | 15 |
| {PenaltyPerHourUSD} | SLAPolicy entity — PenaltyPerHourUSD | 50000 |

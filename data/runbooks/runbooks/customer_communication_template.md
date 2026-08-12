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

# Conduit Shared Risk Group Assessment

## Purpose
Assess whether multiple transport links share a common physical conduit, creating a shared-risk group (SRG) where a single physical event can take out multiple "redundant" links simultaneously.

## When to Use
- After a dual-link failure on the same corridor
- During planned maintenance risk assessment on any transport link
- When reviewing route diversity for SLA-governed services

## Procedure
1. **Identify the failed/target link** (e.g., LINK-SYD-MEL-FIBRE-01)
2. **Query the conduit mapping:** Find which PhysicalConduit the link routes through
3. **Find co-routed links:** Query all other TransportLinks that route through the SAME conduit
4. **Assess impact:** If the "backup" link shares the same conduit, redundancy is illusory
5. **Check historical incidents:** Look for past dual-fibre failures on this conduit (e.g., INC-2025-11-22-0055)

## Escalation
- If both primary and backup links share a conduit: escalate to network planning for route diversity review
- Recommend installing alternate fibres through a physically separate conduit

## Known Shared-Risk Groups
- **CONDUIT-SYD-MEL-INLAND:** LINK-SYD-MEL-FIBRE-01 + LINK-SYD-MEL-FIBRE-02 — both routed through Goulburn. NOT physically diverse.

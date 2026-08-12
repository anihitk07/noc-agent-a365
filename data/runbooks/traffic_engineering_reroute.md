# Runbook: MPLS Traffic Engineering Reroute

## Summary
When a primary MPLS path fails (typically due to a transport link cut), traffic must be rerouted to an alternate (secondary) path. This procedure covers pre-checks, execution, and post-reroute validation.

## Prerequisites
- Root cause has been confirmed (see: `fibre_cut_runbook.md` or `alert_storm_triage_guide.md`)
- An alternate MPLS path exists in the ontology (query `MPLSPath` entities with `PathType = SECONDARY` sharing the same source/destination routers)

## Pre-Reroute Checks

### 1. Verify Alternate Path Availability
- Query ontology for `MPLSPath` entities with same endpoints as the failed path
- Example: if `MPLS-PATH-SYD-MEL-PRIMARY` failed, check `MPLS-PATH-SYD-MEL-SECONDARY`
- Verify the secondary path's constituent `TransportLink` entities are all in `Status = Active`

### 2. Verify Alternate Path Capacity
- Query time-series `UtilizationPct` on the secondary path's transport links from Cosmos DB
- **Safe threshold**: Current utilisation + expected traffic < **80%** of link capacity
- If above 80%: reroute is risky, may cause congestion. Escalate to capacity engineering.

| Current Util | Added Traffic | Total | Decision |
|---|---|---|---|
| < 40% | Any | < 80% | ✅ Safe to reroute |
| 40–60% | Moderate | < 80% | ✅ Proceed with monitoring |
| 60–80% | Any | > 80% | ⚠️ Reroute with caution, enable QoS |
| > 80% | Any | > 100% | ❌ Do not reroute, escalate |

### 3. Verify No Conflicting Maintenance
- Check change management for any scheduled maintenance on the secondary path
- If maintenance is scheduled within 4 hours, consider deferring reroute or expediting maintenance reschedule

## Reroute Execution

### Automated (Preferred)
1. Agent calls `execute_reroute` tool with parameters:
   - `failed_path_id`: e.g., `MPLS-PATH-SYD-MEL-PRIMARY`
   - `target_path_id`: e.g., `MPLS-PATH-SYD-MEL-SECONDARY`
   - `approval_ref`: compliance agent approval reference
2. System updates MPLS TE tunnel head-end configuration
3. RSVP-TE signals the new path
4. Traffic shifts within 50ms (make-before-break)

### Manual (Fallback)
1. SSH to head-end router (e.g., `CORE-SYD-01`)
2. Modify MPLS TE tunnel:
   ```
   router# configure terminal
   router(config)# interface Tunnel0
   router(config-if)# tunnel mpls traffic-eng path-option 10 explicit name SYD-MEL-SECONDARY
   router(config-if)# no tunnel mpls traffic-eng path-option 1 explicit name SYD-MEL-PRIMARY
   router(config-if)# end
   router# write memory
   ```
3. Verify tunnel is up: `show mpls traffic-eng tunnels name Tunnel0`

## Post-Reroute Validation
1. **Verify traffic is flowing** — Check UtilizationPct on the new path (should increase)
2. **Verify services are restored** — Query ontology for Service entities that DEPEND_ON the rerouted MPLS path. Check for resolution of SERVICE_DEGRADATION alerts.
3. **Check latency** — The secondary path may have different latency characteristics. Verify LatencyMs is within SLA thresholds.
4. **Update ticket** — Record the reroute in the incident ticket with timestamp, path IDs, and pre/post metrics.

## Rollback
If the reroute causes issues (congestion, latency violation):
1. Revert to the original path configuration
2. Escalate to capacity engineering for traffic balancing
3. Consider partial reroute (only critical services)

## Related Runbooks
- `fibre_cut_runbook.md`
- `customer_communication_template.md`

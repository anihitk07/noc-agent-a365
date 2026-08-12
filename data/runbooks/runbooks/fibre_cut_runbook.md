# Runbook: Fibre Cut — Detection, Verification, and Recovery

## Summary
A fibre cut is a physical-layer failure on a DWDM or dark-fibre transport link, typically caused by third-party dig activity, severe weather, or equipment failure at an amplifier site. It results in total loss of light on the affected span and cascading failures across all logical resources routed over that fibre.

## Detection Criteria
| Indicator | Threshold | Source |
|---|---|---|
| Optical power | < −30 dBm (loss of light) | TransportLink entity — OpticalPowerDbm |
| Bit error rate | = 1.0 (total) | TransportLink entity — BitErrorRate |
| Link status | DOWN | LINK_DOWN alert in telemetry database |
| BGP peer loss | Peer unreachable within 3s of link alarm | BGP_PEER_LOSS alert correlated by time |
| OSPF adjacency | Lost within 5s of link alarm | OSPF_ADJACENCY_DOWN alert |

## Verification Steps
1. **Confirm loss of light** — Query ontology for the TransportLink entity instance. Check time-series OpticalPowerDbm property. If < −30 dBm, loss of light is confirmed.
2. **Rule out transceiver failure** — Check if both ends report loss of light. Query both SourceRouterId and TargetRouterId CoreRouter entities for interface alarm status. If both ends are dark → fibre cut (not single-end transceiver failure).
3. **Check for maintenance window** — Query change management system. If a planned maintenance window is active on this link, this may be expected. Escalate to change coordinator.
4. **Confirm no loopback** — Verify the link is not in a loopback test configuration.

## Immediate Actions
1. **Suppress downstream alerts** — All alerts from nodes downstream of the cut link are symptoms, not independent faults. Suppress to reduce noise.
2. **Assess alternate path** — Query ontology for TransportLink entities between the same SourceRouterId and TargetRouterId. Check UtilizationPct time-series on alternate links.
3. **Initiate traffic reroute** — If alternate path utilisation < 80%, initiate MPLS path failover to secondary path. See: `traffic_engineering_reroute.md`.
4. **Raise P1 incident** — Create priority-1 incident with root cause, blast radius, and estimated SLA impact.

## Escalation
- **L1**: NOC operator verifies and initiates reroute (automated in autonomous mode)
- **L2**: Transport engineering team dispatched for physical repair
- **L3**: Vendor engagement if amplifier or ROADM failure suspected
- **External**: Field team dispatched to fibre route for physical inspection

## Expected Resolution Time
| Scenario | Typical MTTR |
|---|---|
| Reroute to alternate path (automated) | < 1 minute |
| Physical fibre repair (urban) | 4–8 hours |
| Physical fibre repair (rural) | 12–24 hours |
| Amplifier/ROADM replacement | 2–6 hours |

## Related Runbooks
- `bgp_peer_loss_runbook.md`
- `traffic_engineering_reroute.md`
- `alert_storm_triage_guide.md`
- `customer_communication_template.md`

## Verification — Per-Sensor Fault Localisation

When a transport link has multiple optical sensors along its span, query
SensorReadings for all sensors on the affected link. The fault location
is between the LAST sensor showing normal power and the FIRST sensor
showing loss-of-light.

| Sensor Position | Normal Range | Degraded | Cut (loss of light) |
|----------------|-------------|----------|---------------------|
| Head-end splice point | -8 to -12 dBm | < -20 dBm | < -30 dBm |
| Mid-span splice point | -8 to -12 dBm | < -20 dBm | < -30 dBm |
| Tail-end splice point | -8 to -12 dBm | < -20 dBm | < -30 dBm |

### Diagnostic Logic

1. Query the graph for all Sensor entities monitoring the affected TransportLink.
2. Query SensorReadings for each sensor's most recent readings.
3. Identify which sensors show normal power and which show loss-of-light.
4. The fault is located between the last normal sensor and the first critical sensor.
5. Dispatch the field engineer to the GPS coordinates of the first critical sensor.

### Shared-Risk Conduit Check

After identifying the cut link, query the graph for PhysicalConduit entities
associated with the link via `routed_through` relationships. Check whether
any other TransportLink entities share the same conduit — these are in a
shared-risk group and may also be affected by the same physical event.

If the "backup" fibre runs through the same conduit as the failed primary,
it is NOT a diverse path. Flag this to the operator and recommend rerouting
to a path that uses a physically separate route.

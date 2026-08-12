# Runbook: BGP Peer Loss — Diagnosis and Recovery

## Summary
A BGP peer loss occurs when an eBGP or iBGP session between two core routers transitions to the IDLE or ACTIVE state, meaning route advertisements are no longer exchanged. This can be caused by an underlying transport failure, a misconfiguration, or a router-level issue.

## Detection Criteria
| Indicator | Threshold | Source |
|---|---|---|
| BGP session state | IDLE / ACTIVE (not ESTABLISHED) | BGP_PEER_LOSS alert |
| Hold timer expiry | Peer not heard for > 90 seconds | Router telemetry |
| Route withdrawals | > 10 prefixes withdrawn within 30s | ROUTE_WITHDRAWAL alerts |

## Diagnostic Decision Tree

```
BGP Peer Loss Detected
│
├── Is the underlying transport link DOWN?
│   ├── YES → Root cause is transport failure, not BGP.
│   │         See: fibre_cut_runbook.md
│   │         BGP will recover automatically when link restores.
│   │
│   └── NO → Continue diagnosis
│
├── Is the remote router reachable via alternate path?
│   ├── YES → Issue is path-specific. Check:
│   │         - Interface errors (CRC, input errors)
│   │         - MTU mismatch
│   │         - ACL blocking BGP (TCP/179)
│   │
│   └── NO → Remote router may be down. Check:
│            - Router CPU/memory (HIGH_CPU alerts)
│            - Power status
│            - Console access
│
├── Are other BGP sessions on the same router also down?
│   ├── YES → Router-level issue. Check:
│   │         - BGP process crash (show bgp process)
│   │         - Memory exhaustion
│   │         - Configuration change in last 30 minutes
│   │
│   └── NO → Session-specific issue. Check:
│            - Peer AS number mismatch
│            - MD5 authentication failure
│            - Maximum prefix limit exceeded
```

## Recovery Actions
1. **If transport link is the root cause** — No BGP-specific action needed. Fix the link; BGP will re-establish automatically (typically within 30–60 seconds of link restoration).
2. **If router process crash** — Restart BGP process: `clear bgp all`. If persistent, escalate to L3.
3. **If configuration issue** — Roll back recent changes. Verify peer configuration matches on both ends.

## Impact Assessment
- Query ontology: which MPLSPath entities use this BGP session's routers?
- Query ontology: which Service entities DEPEND_ON those MPLS paths?
- Check SLAPolicy entities for penalty risk.

## Related Runbooks
- `fibre_cut_runbook.md`
- `alert_storm_triage_guide.md`

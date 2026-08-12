# Design Document — MPLS Backup Path (MPLS-BACKUP-02)

**Document ID:** INFRA-MPLS-002  
**Revision:** 3.0 — 2026-01-15  
**Owner:** IP/MPLS Engineering, Transport Networks  
**Classification:** Internal — Network Operations

---

## 1. Purpose

MPLS-BACKUP-02 is the secondary MPLS transport path between Sydney and Melbourne. It provides traffic protection when the primary path (MPLS-PRIMARY-01, carried on the Sydney–Melbourne DWDM system) is degraded or unavailable. The backup path follows a geographically diverse route via Canberra to avoid common-mode failures (e.g., a single fibre cut on the Hume Highway corridor).

---

## 2. Path Topology

```
Sydney PE (SYD-PE-01)
    │
    ├── 100GE link to SYD-P-02 (Sydney core)
    │
    ├── SYD-P-02 → CBR-P-01 (Canberra) — 290km via Federal Highway/Kings Highway
    │
    ├── CBR-P-01 → MEL-P-03 (Melbourne) — 660km via Hume Highway (south of Canberra)
    │
    └── MEL-P-03 → MEL-PE-01 (Melbourne PE)
```

| Segment | Router A | Router B | Distance | Link Type | Capacity |
|---------|----------|----------|----------|-----------|----------|
| Segment 1 | SYD-PE-01 | SYD-P-02 | 5 km | 100GE (SMF, dark fibre) | 100 Gbps |
| Segment 2 | SYD-P-02 | CBR-P-01 | 290 km | 10GE (leased wavelength) | 10 Gbps |
| Segment 3 | CBR-P-01 | MEL-P-03 | 660 km | 10GE (leased wavelength) | 10 Gbps |
| Segment 4 | MEL-P-03 | MEL-PE-01 | 8 km | 100GE (SMF, dark fibre) | 100 Gbps |

**Bottleneck:** The end-to-end capacity of MPLS-BACKUP-02 is constrained by the 10 Gbps leased wavelength segments (Segments 2 and 3). All traffic exceeding 10 Gbps will be dropped during failover.

---

## 3. Capacity and Traffic Engineering

| Parameter | Value |
|-----------|-------|
| Nominal Capacity | 10 Gbps |
| Usable Capacity (after protocol overhead) | 9.2 Gbps |
| Normal-State Traffic Load | 0.8 Gbps (keep-alive, monitoring, low-priority overflow) |
| Available Failover Capacity | 8.4 Gbps |
| Primary Path Normal Traffic Load | 48 Gbps (peak), 32 Gbps (average) |
| Traffic That Can Be Protected | ~8.4 Gbps of 48 Gbps peak (~17.5%) |

### Traffic Priority During Failover

When MPLS-BACKUP-02 activates, not all traffic from the primary path can be accommodated. Traffic is admitted to the backup path according to the following priority order, enforced by MPLS Traffic Engineering (MPLS-TE) and DiffServ-aware tunnels:

| Priority | Traffic Class | DSCP | Bandwidth Allocation | Notes |
|----------|--------------|------|---------------------|-------|
| 1 (Highest) | Network control (BGP, OSPF, LDP, BFD) | CS6 | 200 Mbps (reserved) | Must always transit — network stability depends on it |
| 2 | Voice and real-time (VoIP, video conferencing) | EF | 1 Gbps (reserved) | Enterprise SLA commitments |
| 3 | Business-critical data (enterprise VPN, MPLS L3VPN) | AF31 | 4 Gbps (reserved) | Tier 1 customer SLA |
| 4 | Standard data (internet transit, CDN) | AF11 | 2 Gbps (best-effort, excess allowed) | Degraded during congestion |
| 5 (Lowest) | Bulk transfer (backup, replication) | BE | Remaining capacity | Dropped first during congestion |

---

## 4. Failover Conditions

MPLS-BACKUP-02 activates automatically when the primary path meets any of the following conditions:

| Condition | Threshold | Detection Method | Activation Delay |
|-----------|-----------|-----------------|------------------|
| Packet loss | > 50% sustained for ≥ 30 seconds | BFD (Bidirectional Forwarding Detection) on primary LSP | 3 seconds after BFD declares down |
| Latency | > 200 ms one-way sustained for ≥ 60 seconds | IP SLA probes (ICMP echo, 5-second interval) | 15 seconds after threshold breach detected |
| Complete path failure | Link down (interface state) | Interface state change trap | Immediate (sub-second via BFD) |
| DWDM channel loss | > 50% of lit channels alarming | NMS correlation rule triggers MPLS path switch | 30 seconds (NMS processing delay) |

### Failover Mechanism

1. **BFD Detection:** BFD runs on the primary LSP with a 300ms detect multiplier (3 × 100ms intervals). When BFD declares the primary path down, the head-end router (SYD-PE-01) performs a fast-reroute (FRR) to the pre-established backup LSP.
2. **Traffic Steering:** Traffic is steered onto MPLS-BACKUP-02 using pre-configured BGP communities. The BGP community `65000:999` is attached to all prefixes that should fail over. When the primary path is down, the backup path's BGP next-hop becomes preferred.
3. **Traffic Shed:** Since the backup path has only 10 Gbps capacity, the PE routers enforce the DiffServ priority table above. Traffic exceeding the backup capacity is tail-dropped starting from Priority 5 (bulk) upward.

### Failback Behaviour

- Failback to the primary path is **manual** by default (operator must clear the maintenance hold-down in the NMS).
- Automatic failback can be enabled via the NMS (setting: `mpls.backup.auto-revert = true`, hold-down timer: 300 seconds). This is currently **disabled** to prevent flapping during intermittent faults.
- Before restoring traffic to the primary path, the operator should verify:
  1. Primary DWDM system is stable (all channels within power budget for ≥10 minutes).
  2. OTDR traces on the affected span show no residual faults.
  3. MPLS LSP is established and BFD is up on the primary path.

---

## 5. BGP Community Tags

| Community | Meaning | Action |
|-----------|---------|--------|
| `65000:100` | Primary path preferred | Traffic routed via MPLS-PRIMARY-01 (normal state) |
| `65000:200` | Backup path preferred | Traffic routed via MPLS-BACKUP-02 (failover state) |
| `65000:999` | Failover-eligible prefix | Prefix will be rerouted to backup path during primary failure |
| `65000:800` | Do not failover | Prefix remains on primary path regardless of state (used for test/monitoring traffic) |

---

## 6. Monitoring and Alerting

| Metric | Normal | Warning | Critical |
|--------|--------|---------|----------|
| Backup path utilisation | < 20% | > 50% | > 80% |
| Backup path latency (one-way) | < 25 ms | > 35 ms | > 50 ms |
| BFD session state | Up | — | Down |
| Failover event count (per week) | 0 | 1–2 | > 2 |

When the backup path is active and carrying failover traffic, the NOC must be notified immediately. A failover event is classified as a **Priority 1 incident** regardless of the traffic volume affected, because it indicates a fault on the primary DWDM system.

---

## 7. Capacity Upgrade Path

The current 10 Gbps bottleneck on Segments 2 and 3 is a known limitation. A capacity upgrade to 100 Gbps is planned for Q3 2026 (project ref: PROJ-MPLS-UPG-2026). The upgrade involves:

1. Provisioning additional wavelengths on the leased fibre (Sydney–Canberra and Canberra–Melbourne).
2. Upgrading CBR-P-01 router line cards from 10GE to 100GE.
3. Estimated cost: $1.2M (leased wavelength charges + hardware).

Until the upgrade is complete, the 10 Gbps constraint must be factored into all capacity planning and incident impact assessments for the Sydney–Melbourne corridor.

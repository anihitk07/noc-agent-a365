# Firmware Upgrade Procedure — Vendor Advisory Response

## Purpose
Guide the firmware upgrade process when a vendor advisory identifies a bug affecting routers in the network.

## When to Use
- When a vendor advisory (Advisory entity) matches a router's current FirmwareVersion
- When observed telemetry anomalies correlate with a known bug pattern
- During scheduled maintenance windows for preventive upgrades

## Procedure
1. **Identify affected routers:** Query Advisory -[affects_version]-> CoreRouter to find all routers running vulnerable firmware
2. **Assess operational impact:** What services depend on paths through these routers? What SLAs are at risk during upgrade?
3. **Schedule upgrade window:**
   - GOLD SLA services: upgrade during pre-approved maintenance window with traffic pre-routed to backup paths
   - SILVER/STANDARD: upgrade during low-traffic period (02:00-06:00 local)
4. **Pre-upgrade checks:**
   - Verify backup path availability and utilisation headroom
   - Confirm rollback firmware image is staged
   - Notify affected customers per SLA notification requirements
5. **Execute upgrade:** Follow vendor-specific upgrade guide (Cisco IOS-XR or Juniper JUNOS)
6. **Post-upgrade verification:**
   - Confirm BGP sessions re-establish
   - Confirm OSPF adjacencies are stable
   - Monitor for 30 minutes for any anomalies

## Known Advisories
- **ADV-CISCO-2025-001 (HIGH):** OSPF flap under BGP churn — upgrade to IOS-XR-7.10.1. Affects CORE-SYD-01, CORE-MEL-01.
- **ADV-CISCO-2025-002 (MEDIUM):** BFD false positive — workaround available (increase BFD interval). Upgrade to IOS-XR-7.10.1.
- **ADV-JUNIPER-2025-001 (HIGH):** LDP reset during ECMP rebalance — upgrade to JUNOS-24.1R1. Affects CORE-BNE-01.

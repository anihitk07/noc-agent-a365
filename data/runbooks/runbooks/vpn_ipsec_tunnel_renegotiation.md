# Runbook: IPsec VPN Tunnel Renegotiation — SA Expiry Causing VPN Flap

**Runbook ID:** NOC-VPN-008  
**Version:** 2.2  
**Last Updated:** 2025-11-05  
**Owner:** Network Operations Centre — Enterprise Services  
**Classification:** Standard Operating Procedure  

---

## Summary

This runbook addresses IPsec VPN tunnel instability caused by Security Association (SA) expiry and renegotiation failures. When an IKE (Internet Key Exchange) Phase 1 or Phase 2 SA reaches its configured lifetime and the renegotiation (rekey) process fails, the VPN tunnel drops and must be re-established. During the tunnel-down period, all traffic traversing the VPN is blackholed, causing a complete service outage for the affected customer.

This procedure specifically covers enterprise VPN services, including the following high-profile customer tunnels:

- **VPN-ACME-CORP** — Primary site-to-site tunnel between ACME Corporation head office and their hosted infrastructure in the SYD-DC-01 data centre. Carries ERP, email, and file share traffic. SA lifetime: 86400 seconds (24 hours) Phase 1, 3600 seconds (1 hour) Phase 2.
- **VPN-ACME-CORP-DR** — Disaster recovery tunnel from ACME Corporation to MEL-DC-02. Normally standby, activates on primary failure.
- **VPN-GLOBEX-01** — Globex Industries primary tunnel.
- **VPN-INITECH-02** — Initech regional office interconnect.

VPN tunnel renegotiation failures are a **control plane / crypto layer problem**. They are caused by IKE negotiation parameter mismatches, certificate expiry, pre-shared key (PSK) discrepancies, or DPD (Dead Peer Detection) false positives. They do **not** indicate transport link failures, fibre cuts, or optical layer faults — the underlying IP connectivity between tunnel endpoints is typically healthy during a renegotiation failure.

**Important:** VPN-ACME-CORP traffic traverses the Sydney–Melbourne transport backbone, including links such as LINK-SYD-MEL. If a fibre cut or transport failure occurs on this backbone, VPN-ACME-CORP will also be affected — but the root cause is the transport layer, not the VPN layer. Always check transport alarm status before diagnosing as a VPN renegotiation issue.

---

## Detection Criteria

| Detection Source | Indicator | Severity | Description |
|---|---|---|---|
| VPN Gateway Syslog | `IKE_SA_EXPIRED` | Warning | Phase 1 SA reached configured lifetime, rekey attempt initiated |
| VPN Gateway Syslog | `IKE_NEGOTIATION_FAILED` | Critical | IKE Phase 1 or Phase 2 negotiation failed — tunnel will drop |
| VPN Gateway Syslog | `IPSEC_SA_DELETE` with no corresponding `IPSEC_SA_CREATE` | Critical | SA deleted (expired) but new SA not established — tunnel is down |
| NMS | `VPN-TUNNEL-DOWN` alarm on VPN-ACME-CORP or other tunnel ID | Critical | Tunnel interface status changed to DOWN |
| Customer Monitoring | Ping loss to customer application servers across VPN | Major | Customer-side monitoring detects reachability loss to hosted services |
| VPN Gateway | DPD timeout (`DPD_PEER_UNREACHABLE`) | Major | Dead Peer Detection declares remote endpoint unreachable — may trigger tunnel teardown |

**Key Differentiator from Transport Fault:**  
If the VPN tunnel is down but the underlying IP path between tunnel endpoints is healthy (confirmed by ping/traceroute to the remote VPN gateway public IP), the issue is in the IKE/IPsec negotiation layer. If the underlying IP path is also down, investigate as a transport fault first — the VPN will not recover until the transport path is restored.

---

## Procedure Steps

### Step 1 — Confirm Tunnel Status and Scope (NOC Tier 1, 0–10 min)

1. Check the VPN gateway dashboard for the affected tunnel:
   - Phase 1 (IKE) SA status: `ESTABLISHED` / `EXPIRED` / `NONE`
   - Phase 2 (IPsec) SA status: `ESTABLISHED` / `EXPIRED` / `NONE`
   - Last successful rekey timestamp
   - Tunnel interface operational status: `UP` / `DOWN`
2. Identify which customer tunnel(s) are affected (e.g., VPN-ACME-CORP, VPN-GLOBEX-01).
3. Check for transport layer alarms on the path between VPN endpoints:
   - If transport alarms are present (link down, optical power loss, fibre cut), escalate to Transport Operations. The VPN issue is a symptom, not the root cause.
   - If no transport alarms, proceed with VPN-layer troubleshooting.

### Step 2 — Diagnose Renegotiation Failure (NOC Tier 2, 10–30 min)

1. Review VPN gateway logs for the failed negotiation sequence. Key log entries to examine:

   **Phase 1 (IKE SA) failure indicators:**
   ```
   IKE: Initiator: proposal mismatch — no matching transform found
   IKE: Authentication failed — pre-shared key mismatch
   IKE: Certificate validation failed — peer certificate expired
   IKE: Retransmission limit reached — peer not responding
   ```

   **Phase 2 (IPsec SA) failure indicators:**
   ```
   IPsec: No proposal chosen — encryption/hash/DH group mismatch
   IPsec: Traffic selector mismatch — local/remote subnet disagreement
   IPsec: PFS group mismatch — DH group negotiation failed
   ```

2. Classify the failure cause:

   | Failure Cause | Log Indicator | Resolution Path |
   |---|---|---|
   | PSK mismatch | `Authentication failed — pre-shared key mismatch` | Verify PSK on both endpoints |
   | Certificate expired | `Certificate validation failed — peer certificate expired` | Renew and deploy certificate |
   | Proposal mismatch | `No matching transform found` or `No proposal chosen` | Align IKE/IPsec proposals on both sides |
   | DPD false positive | `DPD_PEER_UNREACHABLE` but peer is pingable | Adjust DPD interval/timeout |
   | Peer unresponsive | `Retransmission limit reached` | Check remote gateway status, firewall rules, NAT traversal |

### Step 3 — Remediate Based on Root Cause (NOC Tier 2, 30–60 min)

**3a. Pre-Shared Key Mismatch:**
1. Retrieve the current PSK from the key management system for the affected tunnel.
2. Verify the PSK configured on the local VPN gateway matches the key management record.
3. Contact the customer's network administrator (or their managed service provider) to verify the PSK on their endpoint.
4. If a PSK rotation was recently performed and not synchronised, coordinate re-entry of the correct PSK on both endpoints.
5. After PSK correction, initiate an IKE renegotiation:
   ```
   clear crypto isakmp sa <peer-ip>      # Cisco
   request security ike security-associations clear peer <peer-ip>  # Juniper
   ipsec restart                          # Other vendors
   ```

**3b. Certificate Expiry:**
1. Check the expiry date of the certificate used for IKE authentication on the local gateway.
2. If expired, generate a new CSR, submit to the PKI system, and install the renewed certificate.
3. Verify the certificate chain (root CA → intermediate CA → endpoint certificate) is complete and trusted by the peer.
4. After certificate renewal, clear the IKE SA and allow renegotiation.

**3c. Proposal Mismatch:**
1. Compare the IKE and IPsec proposal sets configured on the local gateway with the customer's documented configuration:
   - IKE: encryption algorithm, hash algorithm, DH group, authentication method, SA lifetime
   - IPsec: encryption algorithm, hash algorithm, PFS DH group, SA lifetime
2. Identify the mismatched parameter.
3. If the customer changed their endpoint configuration (firmware upgrade, policy change), coordinate to re-align proposals.
4. Apply the corrected proposal set and renegotiate.

**3d. DPD False Positive:**
1. Review the DPD configuration: interval (seconds between probes) and timeout (seconds before declaring peer dead).
2. If the interval is too aggressive (e.g., 10 seconds interval, 30 seconds timeout), increase to a more conservative setting (e.g., 30 seconds interval, 120 seconds timeout).
3. Verify that DPD packets (UDP 500/4500) are not being rate-limited or dropped by intermediate firewalls or NAT devices.

### Step 4 — Verify Tunnel Restoration (NOC Tier 2, 60–75 min)

1. Confirm Phase 1 and Phase 2 SAs are established:
   ```
   show crypto isakmp sa          # Cisco
   show security ike sa           # Juniper
   show crypto ipsec sa           # Cisco
   show security ipsec sa         # Juniper
   ```
2. Verify encrypted traffic is flowing through the tunnel:
   - Check encaps/decaps packet counters are incrementing.
   - Ping a host on the remote subnet through the tunnel.
3. Confirm with the customer that their applications are restored over the VPN.
4. Monitor the tunnel for the next full SA rekey cycle (Phase 2 lifetime, typically 1 hour) to confirm the next renegotiation succeeds.

### Step 5 — Prevent Recurrence (Engineering, next business day)

1. If PSK rotation was the cause, update the key rotation procedure to include explicit synchronisation verification with the customer before the old SA expires.
2. If certificate expiry was the cause, add a certificate expiry alert at 30, 14, and 7 days before expiry to the monitoring system.
3. If proposal mismatch was caused by customer firmware upgrade, update the customer's VPN configuration file in the configuration management database.
4. Document the incident root cause and resolution in the VPN service knowledge base.

---

## Escalation

| Condition | Escalate To | Timeframe |
|---|---|---|
| VPN tunnel down > 30 min, customer-affecting | Enterprise Service Manager | Within 15 min |
| Customer cannot be reached to coordinate PSK or proposal alignment | Account Manager — customer liaison | Within 30 min |
| Underlying transport path fault confirmed | Transport Operations — fibre/link restoration | Immediate |
| Multiple VPN tunnels failing simultaneously (platform-wide issue) | VPN Platform Engineering | Immediate |
| Certificate authority infrastructure unavailable for renewal | Security Engineering — PKI team | Within 30 min |

---

## Expected Resolution Time

| Scenario | Target Resolution |
|---|---|
| DPD false positive — parameter adjustment | 15–30 min |
| PSK mismatch — key re-synchronisation (customer reachable) | 30–60 min |
| Proposal mismatch — configuration alignment | 30–60 min |
| Certificate expiry — renewal and deployment | 1–2 hours |
| Customer unreachable for coordination | 2–4 hours (dependent on customer response) |
| Transport-layer root cause (fibre cut, link failure) | Per transport runbook (NOC-OPT-003) |

---

## Related Runbooks

- NOC-VPN-003: VPN Tunnel Provisioning — New Customer Setup
- NOC-VPN-012: VPN Performance Degradation — MTU and Fragmentation Issues
- NOC-OPT-003: Fibre Cut — Span Loss Detection and Restoration
- NOC-SEC-025: Certificate Lifecycle Management — Expiry Monitoring and Renewal

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 2.2 | 2025-11-05 | T. Nguyen | Added VPN-ACME-CORP-DR reference, DPD false positive troubleshooting |
| 2.1 | 2025-07-20 | F. Hassan | Updated certificate renewal procedure for new PKI system |
| 2.0 | 2025-03-01 | T. Nguyen | Major revision — added detailed proposal mismatch diagnostics |
| 1.1 | 2024-09-15 | F. Hassan | Added Juniper command syntax alongside Cisco |
| 1.0 | 2024-04-01 | T. Nguyen | Initial version |

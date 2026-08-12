# Runbook: DNS Cache Poisoning — Security Incident Response

**Runbook ID:** NOC-SEC-019  
**Version:** 3.1  
**Last Updated:** 2025-09-30  
**Owner:** Network Operations Centre — Security Operations  
**Classification:** Security Incident Response Procedure  

---

## Summary

This runbook defines the response procedure when DNS cache poisoning is detected or suspected on the network's recursive DNS resolver infrastructure. DNS cache poisoning (also known as DNS spoofing) occurs when an attacker injects forged DNS records into the resolver cache, causing legitimate customer DNS queries to resolve to attacker-controlled IP addresses.

The impact of a successful cache poisoning attack includes:

- Customer traffic redirected to malicious servers (credential harvesting, malware distribution)
- SSL/TLS certificate mismatch warnings for affected domains (if the attacker does not possess valid certificates)
- Degraded customer trust and potential regulatory notification obligations
- Potential for secondary attacks using the redirected traffic (man-in-the-middle, data exfiltration)

This incident type is a **Layer 7 (application layer) security event**. It does not affect the transport network, optical infrastructure, or physical connectivity. Customer access circuits and transport links will show as healthy during a DNS poisoning event — the failure is in name resolution, not in network reachability.

---

## Detection Criteria

| Detection Source | Indicator | Severity | Description |
|---|---|---|---|
| DNS Query Logging | Unexpected TTL values on cached records | Warning | TTL values significantly lower or higher than authoritative server TTL for the same domain |
| DNS Query Logging | Resolution to IP addresses not matching authoritative answer | Critical | Cached A/AAAA records point to IP addresses that differ from the authoritative nameserver response |
| Customer Complaints | SSL certificate warnings on well-known domains | Major | Multiple customers reporting certificate mismatch for the same domain — indicates resolution to wrong IP |
| IDS/IPS | DNS response with mismatched Transaction ID or source port | Critical | Signature match for Kaminsky-style attack attempt |
| DNSSEC Validation | `SERVFAIL` on signed domains | Major | DNSSEC validation failing for domains that were previously resolving — indicates poisoned records failing signature check |
| Threat Intelligence | IOC match on resolved IP address | Critical | Resolved IP matches known malicious infrastructure in threat intelligence feed |

**Key Differentiator from Network Outage:**  
DNS cache poisoning does **not** cause link down alarms, optical power loss, BGP session drops, or any transport-layer indications. If customers report "internet is down" but all transport links and peering sessions are healthy, investigate DNS resolution before assuming a network fault.

---

## Procedure Steps

### Step 1 — Confirm Poisoning (Security Analyst, 0–15 min)

1. Identify the affected domain(s) from customer reports or automated detection.
2. Query the suspected poisoned recursive resolver directly:
   ```
   dig @<resolver-ip> <affected-domain> A +norecurse
   ```
3. Compare the cached answer with the authoritative answer:
   ```
   dig @<authoritative-ns> <affected-domain> A
   ```
4. If the cached answer differs from the authoritative answer, poisoning is confirmed.
5. Check DNSSEC status for the affected domain:
   ```
   dig @<resolver-ip> <affected-domain> A +dnssec +cd
   ```
   If the domain is DNSSEC-signed and the resolver has validation enabled, poisoned records should trigger `SERVFAIL`. If they do not, investigate whether DNSSEC validation is disabled or misconfigured.

### Step 2 — Contain the Incident (Security Analyst + NOC Tier 2, 15–30 min)

1. Flush the poisoned records from the affected resolver cache:
   ```
   rndc flush <affected-domain>       # BIND
   unbound-control flush <affected-domain>  # Unbound
   ```
2. If the scope of poisoning is unclear, flush the entire cache:
   ```
   rndc flush        # BIND — flushes all cached records
   unbound-control reload  # Unbound — reloads and clears cache
   ```
3. Temporarily configure the resolver to forward queries for the affected domain to a known-good upstream resolver (e.g., the authoritative nameserver directly) to prevent re-poisoning:
   ```
   zone "<affected-domain>" {
       type forward;
       forwarders { <authoritative-ns-ip>; };
   };
   ```
4. Enable query logging at maximum verbosity on the affected resolver to capture the attack source:
   ```
   rndc querylog on    # BIND
   ```

### Step 3 — Source Identification (Security Analyst, 30–60 min)

1. Analyse query logs and packet captures to identify the source of the forged DNS responses:
   - Source IP address of the spoofed response packets
   - Transaction ID and source port patterns (sequential vs randomised)
   - Volume and timing of spoofed responses
2. Check whether the source IP is an on-network device (compromised server, compromised CPE) or an off-network attacker.
3. If on-network: isolate the source device immediately (port shutdown, ACL block).
4. If off-network: apply ingress filtering on the peering/transit interfaces to drop spoofed DNS responses from the attacker source.

### Step 4 — Hardening and Prevention (Security Engineering, 60–120 min)

1. Verify the following DNS resolver hardening measures are active:
   - **Source port randomisation:** resolver uses random source ports for outbound queries (not a fixed port).
   - **Transaction ID randomisation:** resolver uses random 16-bit Transaction IDs.
   - **DNSSEC validation:** enabled and enforced for all signed domains.
   - **Response Rate Limiting (RRL):** configured to limit the rate of identical responses.
   - **0x20 encoding:** case randomisation of query names for additional entropy (if supported by resolver software).
2. If any hardening measure is missing, implement it immediately and document the gap in the incident report.
3. Consider deploying DNS-over-HTTPS (DoH) or DNS-over-TLS (DoT) for customer-facing resolvers to prevent on-path response injection.

### Step 5 — Customer Notification and Closeout (Service Management, concurrent)

1. If customer traffic was confirmed redirected to malicious infrastructure:
   - Issue a customer advisory recommending password changes for any services accessed during the poisoning window.
   - Notify the security team to assess whether regulatory breach notification is required.
2. Generate an incident report including: timeline, affected domains, attack vector, containment actions, and hardening improvements.
3. Close the security incident ticket with root cause, impact assessment, and remediation evidence.

---

## Escalation

| Condition | Escalate To | Timeframe |
|---|---|---|
| Poisoning confirmed and affecting customer-facing domains | Security Incident Commander | Immediate |
| Source of forged responses is an on-network compromised device | Security Operations — device forensics | Within 15 min |
| DNSSEC validation bypassed (poisoned records accepted despite valid DNSSEC) | DNS Engineering — resolver software bug investigation | Immediate |
| Customer data potentially exfiltrated via redirected traffic | CISO / Legal — regulatory notification assessment | Within 1 hour |
| Poisoning recurs after cache flush | Security Engineering — persistent attack, additional containment required | Within 15 min of recurrence |

---

## Expected Resolution Time

| Scenario | Target Resolution |
|---|---|
| Single domain poisoned, cache flushed, no re-poisoning | 30–60 min |
| Multiple domains poisoned, source identified and blocked | 1–2 hours |
| On-network compromised device as source, device isolated | 2–4 hours (including forensic preservation) |
| Persistent off-network attacker, requires upstream filtering | 4–8 hours |

---

## Related Runbooks

- NOC-SEC-015: DDoS Mitigation — Volumetric Attack Response
- NOC-SEC-022: Compromised Customer CPE — Isolation and Remediation
- NOC-NET-005: BGP Hijack Detection and Response
- NOC-DNS-001: Recursive Resolver Failover and Capacity Management

---

## Revision History

| Version | Date | Author | Change |
|---|---|---|---|
| 3.1 | 2025-09-30 | A. Mahmoud | Added DoH/DoT recommendation, updated detection criteria |
| 3.0 | 2025-05-15 | L. Reyes | Major revision — added DNSSEC bypass escalation path |
| 2.1 | 2024-12-01 | A. Mahmoud | Updated containment procedure for Unbound resolvers |
| 2.0 | 2024-07-20 | L. Reyes | Added source identification procedure |
| 1.0 | 2024-01-10 | A. Mahmoud | Initial version |

"""
Generate deterministic CSV telemetry tables from the synthetic incident tickets.

Reads the existing ticket corpus under data/tickets/ plus the real sensor/link
dimension tables under data/ontology_entities/, then writes:
  - data/telemetry/OpticalTelemetry.csv
  - data/telemetry/NetworkAlerts.csv
  - data/telemetry/IncidentEvents.csv

No network calls, no non-stdlib dependencies.
"""

from __future__ import annotations

import csv
import random
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TICKETS_DIR = REPO_ROOT / "data" / "tickets"
SENSORS_CSV = REPO_ROOT / "data" / "ontology_entities" / "DimSensor.csv"
LINKS_CSV = REPO_ROOT / "data" / "ontology_entities" / "DimTransportLink.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "telemetry"
RANDOM_SEED = 42
INTERVAL_SECONDS = 10
WINDOW_PADDING_SECONDS = 60


@dataclass(frozen=True)
class Sensor:
    sensor_id: str
    sensor_type: str
    link_id: str


@dataclass(frozen=True)
class Trace:
    values: tuple[float, ...]
    note: str = ""
    duration_seconds: int | None = None

    def value_at(self, when: datetime, start: datetime, end: datetime) -> float:
        if len(self.values) == 1 or end <= start:
            return self.values[0]

        total = max((end - start).total_seconds(), 1.0)
        elapsed = min(max((when - start).total_seconds(), 0.0), total)
        progress = elapsed / total

        if len(self.values) == 2:
            return self.values[0] + (self.values[1] - self.values[0]) * progress

        note = self.note.lower()
        if "recover" in note or "planned cycle" in note or "spike" in note:
            midpoint = start + timedelta(seconds=self.duration_seconds or total)
            midpoint = min(midpoint, end)
            first_leg = max((midpoint - start).total_seconds(), 1.0)
            if when <= midpoint:
                leg_progress = min(max((when - start).total_seconds(), 0.0), first_leg) / first_leg
                return self.values[0] + (self.values[1] - self.values[0]) * leg_progress
            second_leg = max((end - midpoint).total_seconds(), 1.0)
            leg_progress = min(max((when - midpoint).total_seconds(), 0.0), second_leg) / second_leg
            return self.values[1] + (self.values[2] - self.values[1]) * leg_progress

        if "progressive decline" in note:
            decline_seconds = self.duration_seconds or min(int(total), 900)
            decline_end = min(start + timedelta(seconds=decline_seconds), end)
            first_leg = max((decline_end - start).total_seconds(), 1.0)
            if when <= decline_end:
                halfway = start + timedelta(seconds=first_leg / 2)
                if when <= halfway:
                    leg_progress = min(max((when - start).total_seconds(), 0.0), first_leg / 2) / max(
                        first_leg / 2, 1.0
                    )
                    return self.values[0] + (self.values[1] - self.values[0]) * leg_progress
                leg_progress = min(max((when - halfway).total_seconds(), 0.0), first_leg / 2) / max(
                    first_leg / 2, 1.0
                )
                return self.values[1] + (self.values[2] - self.values[1]) * leg_progress
            return self.values[2]

        # ponytail: three-point traces use a simple symmetric interpolation unless
        # the note clearly says "recover" or "progressive decline".
        halfway = start + timedelta(seconds=total / 2)
        if when <= halfway:
            leg_progress = min(max((when - start).total_seconds(), 0.0), total / 2) / max(total / 2, 1.0)
            return self.values[0] + (self.values[1] - self.values[0]) * leg_progress
        leg_progress = min(max((when - halfway).total_seconds(), 0.0), total / 2) / max(total / 2, 1.0)
        return self.values[1] + (self.values[2] - self.values[1]) * leg_progress


@dataclass
class Ticket:
    incident_id: str
    path: Path
    title: str
    severity: str
    root_cause: str
    root_cause_type: str
    created: datetime
    resolved: datetime
    alerts_generated: int
    alerts_suppressed: int
    detect_delay_seconds: int | None
    description: str
    detection_method: str
    resolution: str
    signature_lines: list[str]
    zero_alert_text: bool
    sensor_traces: dict[str, Trace] = field(default_factory=dict)
    link_power_hints: dict[str, list[Trace]] = field(default_factory=dict)
    link_ber_traces: dict[str, Trace] = field(default_factory=dict)
    link_util_traces: dict[str, Trace] = field(default_factory=dict)
    entities: list[str] = field(default_factory=list)


def log_message(message: str) -> None:
    print(message, flush=True)


def parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def parse_delay(value: str) -> int | None:
    text = value.strip()
    if text.startswith("N/A"):
        return None
    number = re.search(r"(\d+(?:\.\d+)?)", text)
    if not number:
        return None
    amount = float(number.group(1))
    lowered = text.lower()
    if "hour" in lowered:
        return int(amount * 3600)
    if "min" in lowered:
        return int(amount * 60)
    return int(amount)


def parse_duration_seconds(text: str) -> int | None:
    lowered = text.lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*(second|seconds|sec|minute|minutes|min|hour|hours|hr)", lowered)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    if unit.startswith(("hour", "hr")):
        return int(amount * 3600)
    if unit.startswith(("minute", "min")):
        return int(amount * 60)
    return int(amount)


def parse_trace_values(line: str, unit_pattern: str) -> tuple[float, ...]:
    matches = re.findall(unit_pattern, line)
    return tuple(float(match.replace(",", "")) for match in matches)


def extract_section(text: str, heading: str, next_heading: str) -> str:
    match = re.search(rf"{re.escape(heading)}:\r?\n(.*?)(?:\r?\n\r?\n{re.escape(next_heading)}:)", text, re.S)
    return match.group(1).strip() if match else ""


def load_optical_sensors() -> dict[str, Sensor]:
    sensors: dict[str, Sensor] = {}
    with SENSORS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["SensorType"] != "OpticalPower":
                continue
            sensors[row["SensorId"]] = Sensor(
                sensor_id=row["SensorId"],
                sensor_type=row["SensorType"],
                link_id=row["MonitoredEntityId"],
            )
    return sensors


def load_links() -> set[str]:
    with LINKS_CSV.open(newline="", encoding="utf-8") as handle:
        return {row["LinkId"] for row in csv.DictReader(handle)}


def parse_ticket(path: Path, optical_sensors: dict[str, Sensor], known_links: set[str]) -> Ticket:
    text = path.read_text(encoding="utf-8")
    incident_id = re.search(r"^Incident:\s*(.+)$", text, re.M).group(1)
    title = re.search(r"^Title:\s*(.+)$", text, re.M).group(1)
    severity = re.search(r"^Severity:\s*(.+)$", text, re.M).group(1)
    root_cause = re.search(r"^Root Cause:\s*(.+)$", text, re.M).group(1)
    root_cause_type = re.search(r"^Root Cause Type:\s*(.+)$", text, re.M).group(1)
    created = parse_iso8601(re.search(r"^Created:\s*(.+)$", text, re.M).group(1))
    resolved = parse_iso8601(re.search(r"^Resolved:\s*(.+)$", text, re.M).group(1))
    alerts_generated = int(re.search(r"^Alerts Generated:\s*(\d+)$", text, re.M).group(1))
    alerts_suppressed = int(re.search(r"^Alerts Suppressed:\s*(\d+)$", text, re.M).group(1))
    detect_delay_seconds = parse_delay(re.search(r"^Time to Detect:\s*(.+)$", text, re.M).group(1))
    signature = re.search(r"Telemetry Signature:\r?\n(.*?)(?:\r?\nCreated:)", text, re.S).group(1).strip()
    signature_lines = [line.rstrip() for line in signature.splitlines()]
    description = extract_section(text, "Description", "Detection Method")
    detection_method = extract_section(text, "Detection Method", "Resolution")
    resolution = extract_section(text, "Resolution", "Customer Impact")
    zero_alert_text = alerts_generated == 0 and (
        "no network-side alerts" in text.lower() or "alerts generated: 0" in text.lower()
    )

    ticket = Ticket(
        incident_id=incident_id,
        path=path,
        title=title,
        severity=severity,
        root_cause=root_cause,
        root_cause_type=root_cause_type,
        created=created,
        resolved=resolved,
        alerts_generated=alerts_generated,
        alerts_suppressed=alerts_suppressed,
        detect_delay_seconds=detect_delay_seconds,
        description=description,
        detection_method=detection_method,
        resolution=resolution,
        signature_lines=signature_lines,
        zero_alert_text=zero_alert_text,
    )

    entity_candidates: list[str] = [root_cause]
    link_candidates = set(re.findall(r"(LINK-[A-Z0-9-]+)", signature))
    if root_cause in known_links:
        link_candidates.add(root_cause)
    entity_candidates.extend(sorted(link_candidates))

    for raw_line in signature_lines:
        line = raw_line.strip()
        sensor_match = re.match(r"(SENS-[A-Z0-9-]+).*?:\s*(.+)", line)
        if sensor_match:
            sensor_id = sensor_match.group(1)
            entity_candidates.append(sensor_id)
            if sensor_id in optical_sensors:
                values = parse_trace_values(line, r"(-?\d+(?:\.\d+)?)\s*dBm")
                if values:
                    ticket.sensor_traces[sensor_id] = Trace(
                        values=values,
                        note=line[line.rfind("(") + 1 : line.rfind(")")] if "(" in line and ")" in line else "",
                        duration_seconds=parse_duration_seconds(line),
                    )
            continue

        ber_match = re.match(r"(LINK-[A-Z0-9-]+).*?BER:\s*(.+)", line)
        if ber_match:
            link_id = ber_match.group(1)
            values = parse_trace_values(ber_match.group(2), r"(\d+(?:\.\d+)?e[+-]?\d+|\d+(?:\.\d+)?)")
            if values:
                ticket.link_ber_traces[link_id] = Trace(
                    values=values,
                    note=line[line.rfind("(") + 1 : line.rfind(")")] if "(" in line and ")" in line else "",
                    duration_seconds=parse_duration_seconds(line),
                )
                entity_candidates.append(link_id)
            continue

        util_match = re.match(r"(LINK-[A-Z0-9-]+).*?Utilization:\s*(.+)", line)
        if util_match:
            link_id = util_match.group(1)
            values = parse_trace_values(line, r"(\d+(?:\.\d+)?)%")
            if values:
                ticket.link_util_traces[link_id] = Trace(
                    values=values,
                    note=line[line.rfind("(") + 1 : line.rfind(")")] if "(" in line and ")" in line else "",
                    duration_seconds=parse_duration_seconds(line),
                )
                entity_candidates.append(link_id)
            continue

        power_match = re.match(r"(LINK-[A-Z0-9-]+).*?optical power.*?:\s*(.+)", line, re.I)
        if power_match:
            link_id = power_match.group(1)
            values = parse_trace_values(line, r"(-?\d+(?:\.\d+)?)\s*dBm")
            if values:
                ticket.link_power_hints.setdefault(link_id, []).append(
                    Trace(
                        values=values,
                        note=line[line.rfind("(") + 1 : line.rfind(")")] if "(" in line and ")" in line else "",
                        duration_seconds=parse_duration_seconds(line),
                    )
                )
                entity_candidates.append(link_id)

    ticket.entities = list(dict.fromkeys(entity_candidates))
    return ticket


def collect_tickets(optical_sensors: dict[str, Sensor], known_links: set[str]) -> list[Ticket]:
    return [parse_ticket(path, optical_sensors, known_links) for path in sorted(TICKETS_DIR.glob("*.txt"))]


def compute_sensor_baselines(tickets: list[Ticket], optical_sensors: dict[str, Sensor]) -> dict[str, float]:
    baselines: dict[str, float] = {}
    hints_by_link: dict[str, list[float]] = {}
    for ticket in tickets:
        for sensor_id, trace in ticket.sensor_traces.items():
            baselines.setdefault(sensor_id, trace.values[0])
        for link_id, traces in ticket.link_power_hints.items():
            hints_by_link.setdefault(link_id, []).extend(trace.values[:1] for trace in traces)

    flattened_hints: dict[str, list[float]] = {}
    for link_id, lists in hints_by_link.items():
        flattened_hints[link_id] = [item for sublist in lists for item in sublist]

    link_avg: dict[str, float] = {}
    for sensor_id, sensor in optical_sensors.items():
        if sensor_id in baselines:
            link_avg.setdefault(sensor.link_id, 0.0)
    for link_id in {sensor.link_id for sensor in optical_sensors.values()}:
        direct = [value for sensor_id, value in baselines.items() if optical_sensors[sensor_id].link_id == link_id]
        if direct:
            link_avg[link_id] = sum(direct) / len(direct)
        elif flattened_hints.get(link_id):
            link_avg[link_id] = sum(flattened_hints[link_id]) / len(flattened_hints[link_id])
        else:
            link_avg[link_id] = -10.5

    for link_id, sensor_ids in group_sensors_by_link(optical_sensors).items():
        hint_values = flattened_hints.get(link_id, [])
        for index, sensor_id in enumerate(sensor_ids):
            if sensor_id in baselines:
                continue
            if index < len(hint_values):
                baselines[sensor_id] = hint_values[index]
            else:
                baselines[sensor_id] = link_avg[link_id] - (0.15 * index)

    return baselines


def compute_link_baselines(
    tickets: list[Ticket], optical_sensors: dict[str, Sensor]
) -> tuple[dict[str, float], dict[str, float]]:
    ber: dict[str, float] = {}
    util: dict[str, float] = {}
    for ticket in tickets:
        for link_id, trace in ticket.link_ber_traces.items():
            ber.setdefault(link_id, trace.values[0])
        for link_id, trace in ticket.link_util_traces.items():
            util.setdefault(link_id, trace.values[0])

    for link_id in group_sensors_by_link(optical_sensors):
        ber.setdefault(link_id, 2.0e-12)
        util.setdefault(link_id, 45.0)

    return ber, util


def group_sensors_by_link(optical_sensors: dict[str, Sensor]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for sensor_id, sensor in optical_sensors.items():
        grouped.setdefault(sensor.link_id, []).append(sensor_id)
    for sensor_ids in grouped.values():
        sensor_ids.sort()
    return grouped


def expand_link_power_hints(tickets: list[Ticket], grouped_sensors: dict[str, list[str]]) -> None:
    for ticket in tickets:
        for link_id, traces in ticket.link_power_hints.items():
            sensor_ids = [sensor_id for sensor_id in grouped_sensors.get(link_id, []) if sensor_id not in ticket.sensor_traces]
            for sensor_id, trace in zip(sensor_ids, traces):
                ticket.sensor_traces.setdefault(sensor_id, trace)


def stable_noise(label: str, when: datetime, amplitude: float) -> float:
    rng = random.Random(f"{RANDOM_SEED}:{label}:{when.isoformat()}")
    return rng.uniform(-amplitude, amplitude)


def build_optical_rows(
    tickets: list[Ticket],
    optical_sensors: dict[str, Sensor],
    sensor_baselines: dict[str, float],
    link_ber_baselines: dict[str, float],
    link_util_baselines: dict[str, float],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    emitted: set[tuple[str, str]] = set()

    for ticket in tickets:
        window_start = ticket.created - timedelta(seconds=WINDOW_PADDING_SECONDS)
        window_end = ticket.resolved + timedelta(seconds=WINDOW_PADDING_SECONDS)
        when = window_start
        while when <= window_end:
            for sensor_id, sensor in sorted(optical_sensors.items()):
                key = (when.isoformat(), sensor_id)
                if key in emitted:
                    continue
                emitted.add(key)

                power = sensor_baselines[sensor_id] + stable_noise(sensor_id, when, 0.03)
                if ticket.created <= when <= ticket.resolved and sensor_id in ticket.sensor_traces:
                    # ponytail: linear/piecewise interpolation is enough for demo KQL
                    # queries; swap in a physical attenuation curve only if needed.
                    power = ticket.sensor_traces[sensor_id].value_at(when, ticket.created, ticket.resolved)
                ber = link_ber_baselines[sensor.link_id] * (1 + stable_noise(f"ber:{sensor.link_id}", when, 0.08))
                if ticket.created <= when <= ticket.resolved and sensor.link_id in ticket.link_ber_traces:
                    ber = ticket.link_ber_traces[sensor.link_id].value_at(when, ticket.created, ticket.resolved)
                util = link_util_baselines[sensor.link_id] + stable_noise(f"util:{sensor.link_id}", when, 1.2)
                if ticket.created <= when <= ticket.resolved and sensor.link_id in ticket.link_util_traces:
                    util = ticket.link_util_traces[sensor.link_id].value_at(when, ticket.created, ticket.resolved)

                rows.append(
                    {
                        "Timestamp": to_zulu(when),
                        "SensorId": sensor_id,
                        "LinkId": sensor.link_id,
                        "PowerDbm": f"{power:.3f}",
                        "Ber": f"{max(ber, 1e-15):.6e}",
                        "UtilizationPct": f"{min(max(util, 0.0), 100.0):.3f}",
                    }
                )
            when += timedelta(seconds=INTERVAL_SECONDS)

    rows.sort(key=lambda row: (row["Timestamp"], row["SensorId"]))
    return rows


def choose_alert_types(ticket: Ticket) -> list[str]:
    root = ticket.root_cause_type
    if "FIBRE" in root or "OPTICAL" in root or "AMPLIFIER" in root:
        return ["LOSS_OF_LIGHT", "BER_THRESHOLD", "SERVICE_DEGRADATION"]
    if "POWER" in root:
        return ["POWER_FEED", "SITE_REACHABILITY", "UPS_EVENT"]
    if "BGP" in root or "OSPF" in root or "SOFTWARE" in root:
        return ["ROUTING_PROTOCOL", "CONTROL_PLANE", "SERVICE_DEGRADATION"]
    if "MAINTENANCE" in root:
        return ["MAINTENANCE_WINDOW", "CHANGE_NOTICE"]
    if "CAPACITY" in root:
        return ["CAPACITY_THRESHOLD", "QOS_DROP", "SERVICE_DEGRADATION"]
    return ["GENERIC_NOC_ALERT"]


def alert_actor(ticket: Ticket) -> str:
    if "planned event" in ticket.detection_method.lower() or "change management" in ticket.detection_method.lower():
        return "change.bot"
    if ticket.alerts_generated == 0:
        return "external.reporter"
    if ticket.severity == "P1":
        return "noc.major-incident"
    return "noc.oncall"


def build_alert_rows(tickets: list[Ticket]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for ticket in tickets:
        if ticket.alerts_generated == 0:
            continue
        detect_at = ticket.created + timedelta(seconds=ticket.detect_delay_seconds or 0)
        ack_delay = 0 if "planned event" in ticket.detection_method.lower() else {"P1": 30, "P2": 90, "P3": 180}.get(
            ticket.severity, 300
        )
        ack_at = min(ticket.resolved, detect_at + timedelta(seconds=ack_delay))
        alert_types = choose_alert_types(ticket)
        entities = ticket.entities or [ticket.root_cause]
        unsuppressed = max(ticket.alerts_generated - ticket.alerts_suppressed, 0)

        for index in range(ticket.alerts_generated):
            suppressed = index >= unsuppressed
            offset = index % 20
            alert_time = detect_at + timedelta(seconds=offset)
            # ponytail: tickets do not carry explicit ack timestamps, so we derive a
            # small deterministic ack delay from severity/detection mode.
            rows.append(
                {
                    "Timestamp": to_zulu(alert_time),
                    "AlertId": f"ALT-{ticket.incident_id}-{index + 1:04d}",
                    "IncidentId": ticket.incident_id,
                    "EntityId": entities[index % len(entities)],
                    "Severity": ticket.severity,
                    "AlertType": alert_types[index % len(alert_types)],
                    "Suppressed": "true" if suppressed else "false",
                    "AckedAt": "" if suppressed else to_zulu(ack_at),
                    "AckedBy": "" if suppressed else alert_actor(ticket),
                }
            )

    rows.sort(key=lambda row: (row["Timestamp"], row["AlertId"]))
    return rows


def build_event_rows(tickets: list[Ticket]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for ticket in tickets:
        created = ticket.created
        detect_at = created + timedelta(seconds=ticket.detect_delay_seconds or 0)
        ack_delay = 0 if ticket.alerts_generated == 0 else {"P1": 30, "P2": 90, "P3": 180}.get(ticket.severity, 300)
        ack_at = min(ticket.resolved, detect_at + timedelta(seconds=ack_delay))
        rows.append(
            {
                "Timestamp": to_zulu(created),
                "IncidentId": ticket.incident_id,
                "Stage": "Detected",
                "Detail": ticket.detection_method,
                "Actor": "monitoring" if ticket.alerts_generated else "external.reporter",
            }
        )
        rows.append(
            {
                "Timestamp": to_zulu(ack_at),
                "IncidentId": ticket.incident_id,
                "Stage": "Acknowledged",
                "Detail": f"{ticket.severity} incident acknowledged",
                "Actor": alert_actor(ticket),
            }
        )
        if ticket.severity in {"P1", "P2"} or ticket.alerts_generated >= 100:
            escalate_at = min(ticket.resolved, ack_at + timedelta(minutes=2))
            rows.append(
                {
                    "Timestamp": to_zulu(escalate_at),
                    "IncidentId": ticket.incident_id,
                    "Stage": "Escalated",
                    "Detail": ticket.title,
                    "Actor": "major-incident-manager" if ticket.severity == "P1" else "noc.lead",
                }
            )
        rows.append(
            {
                "Timestamp": to_zulu(ticket.resolved),
                "IncidentId": ticket.incident_id,
                "Stage": "Resolved",
                "Detail": first_sentence(ticket.resolution or ticket.description),
                "Actor": "field.team" if "field" in (ticket.resolution + ticket.description).lower() else "noc.oncall",
            }
        )
    rows.sort(key=lambda row: (row["Timestamp"], row["IncidentId"], row["Stage"]))
    return rows


def first_sentence(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return "Resolved"
    sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0]
    return sentence[:180]


def to_zulu(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_self_check(tickets: list[Ticket], alerts_path: Path) -> None:
    ticket_ids = {ticket.incident_id for ticket in tickets}
    zero_alert_ids = {
        ticket.incident_id
        for ticket in tickets
        if ticket.zero_alert_text
        or "zero telemetry anomalies detected" in ticket.path.read_text(encoding="utf-8").lower()
        or "no network-side alerts were generated" in ticket.path.read_text(encoding="utf-8").lower()
    }
    with alerts_path.open(newline="", encoding="utf-8") as handle:
        alerts = list(csv.DictReader(handle))

    alert_incident_ids = {row["IncidentId"] for row in alerts}
    assert alert_incident_ids <= ticket_ids, "NetworkAlerts.csv referenced an unknown incident id"
    alert_counts: dict[str, int] = {}
    for row in alerts:
        alert_counts[row["IncidentId"]] = alert_counts.get(row["IncidentId"], 0) + 1
    for incident_id in zero_alert_ids:
        assert alert_counts.get(incident_id, 0) == 0, f"{incident_id} should have zero alert rows"


def main() -> None:
    log_message("Loading ticket and dimension data...")
    optical_sensors = load_optical_sensors()
    known_links = load_links()
    tickets = collect_tickets(optical_sensors, known_links)
    grouped_sensors = group_sensors_by_link(optical_sensors)
    expand_link_power_hints(tickets, grouped_sensors)
    sensor_baselines = compute_sensor_baselines(tickets, optical_sensors)
    link_ber_baselines, link_util_baselines = compute_link_baselines(tickets, optical_sensors)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    optical_rows = build_optical_rows(tickets, optical_sensors, sensor_baselines, link_ber_baselines, link_util_baselines)
    alert_rows = build_alert_rows(tickets)
    event_rows = build_event_rows(tickets)

    optical_path = OUTPUT_DIR / "OpticalTelemetry.csv"
    alerts_path = OUTPUT_DIR / "NetworkAlerts.csv"
    events_path = OUTPUT_DIR / "IncidentEvents.csv"
    write_csv(
        optical_path,
        optical_rows,
        ["Timestamp", "SensorId", "LinkId", "PowerDbm", "Ber", "UtilizationPct"],
    )
    write_csv(
        alerts_path,
        alert_rows,
        ["Timestamp", "AlertId", "IncidentId", "EntityId", "Severity", "AlertType", "Suppressed", "AckedAt", "AckedBy"],
    )
    write_csv(events_path, event_rows, ["Timestamp", "IncidentId", "Stage", "Detail", "Actor"])

    run_self_check(tickets, alerts_path)
    log_message(
        "Generated telemetry tables: "
        f"{len(optical_rows)} optical rows, {len(alert_rows)} alert rows, {len(event_rows)} event rows."
    )


if __name__ == "__main__":
    main()

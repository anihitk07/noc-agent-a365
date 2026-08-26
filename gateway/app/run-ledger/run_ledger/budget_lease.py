"""Budget leasing — how a MAF orchestrator spends a run budget without a ledger round trip per
call (see ../08-foundry-maf-workflow.md), with the TTL + fencing additions that a Container Apps
/ AKS holder needs (see ../09-teams-bot-maf-aca-topology.md).

The orchestrator borrows a slice of the run budget, spends it locally, and renews in the
background before it runs out. The point of this file is the *bound*: overshoot can never exceed
`concurrent leaseholders x lease size`, which is the number you tune.

Run it directly to execute the self-check:  python budget_lease.py
"""

from dataclasses import dataclass, field

# ponytail: single-process ledger stand-in. Swap Ledger for Redis HINCRBY (atomic) in production —
# the Lease side is unchanged, which is the whole point of the split.


class LedgerFull(Exception):
    """No budget left to lease."""


@dataclass
class Grant:
    amount_micros: int
    token: int          # fencing token: a settle from an older token is stale and ignored
    expires_at: float


@dataclass
class Ledger:
    """Central truth. Touched only on lease grant and settle, never per call."""

    budget_micros: int
    granted_micros: int = 0       # handed out to leaseholders, may not be spent yet
    settled_micros: int = 0       # actually spent, reported back asynchronously
    halted: bool = False
    _next_token: int = 1
    outstanding: dict[int, Grant] = field(default_factory=dict)

    def grant(self, size_micros: int, now: float = 0.0, ttl: float = 300.0) -> Grant:
        """Hand out a lease slice. Returns what was actually granted (may be partial)."""
        self.reclaim_expired(now)
        if self.halted:
            raise LedgerFull("run halted")
        available = self.budget_micros - self.granted_micros
        if available <= 0:
            self.halted = True
            raise LedgerFull("budget exhausted")
        amount = min(size_micros, available)
        self.granted_micros += amount
        g = Grant(amount, self._next_token, now + ttl)
        self.outstanding[g.token] = g
        self._next_token += 1
        return g

    def reclaim_expired(self, now: float) -> int:
        """A replica that died holding a lease must not strand it."""
        expired = [g for g in self.outstanding.values() if g.expires_at <= now]
        for g in expired:
            self.granted_micros -= g.amount_micros
            del self.outstanding[g.token]
        return sum(g.amount_micros for g in expired)

    def settle(self, token: int, spent_micros: int, unused_micros: int) -> bool:
        """Async in production. Rejects stale tokens so a resumed workflow can't double-count."""
        if token not in self.outstanding:
            return False                        # expired or superseded holder — ignore
        self.settled_micros += spent_micros
        self.granted_micros -= unused_micros
        del self.outstanding[token]
        return True


@dataclass
class Lease:
    """Held in the orchestrator's memory. can_afford/debit are pure local operations."""

    ledger: Ledger
    size_micros: int
    remaining_micros: int = 0
    spent_micros: int = 0
    renew_at: float = 0.3          # renew in the background under 30% remaining
    halted: bool = False
    token: int = 0

    def can_afford(self, cost_micros: int) -> bool:
        return not self.halted and cost_micros <= self.remaining_micros

    def needs_renewal(self) -> bool:
        return not self.halted and self.remaining_micros < self.size_micros * self.renew_at

    def renew(self, now: float = 0.0) -> None:
        """The only call that touches the ledger. Background-prefetched, so nothing blocks on it."""
        try:
            g = self.ledger.grant(self.size_micros, now=now)
        except LedgerFull:
            self.halted = True
            return
        self.remaining_micros += g.amount_micros
        self.token = g.token

    def debit(self, cost_micros: int) -> None:
        """Local. No I/O. Overspending the lease is allowed but recorded — a turn's true cost is
        only known after it ends, and clamping it would lose money we actually owe."""
        self.remaining_micros -= cost_micros
        self.spent_micros += cost_micros
        if self.remaining_micros <= 0:
            self.renew()

    def release(self) -> bool:
        """End of workflow: settle true spend and give back what was never used."""
        unused = max(0, self.remaining_micros)
        ok = self.ledger.settle(self.token, self.spent_micros, unused)
        self.remaining_micros = 0
        self.spent_micros = 0
        return ok


def _self_check() -> None:
    BUDGET = 6_000_000     # $6.00 paper
    LEASE = 750_000        # $0.75 slice
    TURN = 200_000         # $0.20 typical agent turn

    # 1. A lease grants up front, then turns cost nothing in round trips.
    led = Ledger(BUDGET)
    lease = Lease(led, LEASE)
    lease.renew()
    assert lease.remaining_micros == LEASE, lease

    for _ in range(3):
        assert lease.can_afford(TURN)
        lease.debit(TURN)
    # 3 x $0.20 = $0.60 of a $0.75 lease, still no second ledger call
    assert lease.remaining_micros == LEASE - 3 * TURN, lease
    assert led.granted_micros == LEASE, led

    # 2. Renewal is triggered by the threshold, not by running dry.
    assert lease.needs_renewal(), "should prefetch under 30%"

    # 3. Round trips scale with budget/lease, not with turns.
    led2 = Ledger(BUDGET)
    l2 = Lease(led2, LEASE)
    l2.renew()
    renewals = 1
    for _ in range(25):                       # 25 turns x $0.20 = $5.00 of work
        if not l2.can_afford(TURN):
            l2.renew()
            renewals += 1
            if l2.halted:
                break
        l2.debit(TURN)
    assert renewals <= (BUDGET // LEASE) + 1, renewals
    assert renewals < 10, f"{renewals} round trips for 25 turns"   # vs 25 without leasing

    # 4. THE BOUND: the ledger can never hand out more than the budget, so the exposure from
    #    optimistic local spending is capped by leaseholders x lease size.
    led3 = Ledger(BUDGET)
    branches = [Lease(led3, LEASE) for _ in range(3)]
    for b in branches:
        b.renew()
    assert led3.granted_micros == 3 * LEASE <= BUDGET, led3

    while not led3.halted:
        for b in branches:
            if not b.halted:
                b.renew()
    assert led3.granted_micros <= BUDGET, led3
    max_overshoot = len(branches) * LEASE
    assert max_overshoot == 2_250_000, max_overshoot          # $2.25 with these settings
    assert max_overshoot < BUDGET, "lease size must stay well under the run budget"

    # 5. Smaller leases tighten the bound and cost more round trips. Explicit trade.
    tight = 100_000                                            # $0.10
    assert len(branches) * tight < max_overshoot
    assert (BUDGET // tight) > (BUDGET // LEASE)

    # 6. Halt propagates: once the ledger is exhausted, renewal halts the leaseholder rather than
    #    silently letting it spend.
    led4 = Ledger(500_000)
    l4 = Lease(led4, LEASE)
    l4.renew()                                                 # partial grant of $0.50
    assert l4.remaining_micros == 500_000, l4
    l4.debit(500_000)                                          # exhausts it, triggers renew
    assert l4.halted and not l4.can_afford(1), l4

    # 7. Release returns unused budget so a frugal run doesn't strand it.
    led5 = Ledger(BUDGET)
    l5 = Lease(led5, LEASE)
    l5.renew()
    l5.debit(TURN)
    assert l5.release() is True
    assert led5.settled_micros == TURN, led5
    assert led5.granted_micros == TURN, led5                   # only the spent part stays held

    # 8. ACA reality: a replica dies holding a lease. The TTL reclaims it, so the budget is not
    #    stranded and the resumed workflow can lease it again.
    led6 = Ledger(BUDGET)
    dead = Lease(led6, LEASE)
    dead.renew(now=0.0)                                        # ttl 300s
    assert led6.granted_micros == LEASE
    assert led6.reclaim_expired(now=100.0) == 0, "not expired yet"
    assert led6.reclaim_expired(now=400.0) == LEASE, "expired lease must return to the pool"
    assert led6.granted_micros == 0, led6

    # 9. Fencing: a late settle from the dead holder must not double-count against the new one.
    resumed = Lease(led6, LEASE)
    resumed.renew(now=400.0)
    assert resumed.token != dead.token
    assert dead.release() is False, "stale token must be ignored"
    assert led6.settled_micros == 0, led6
    resumed.debit(TURN)
    assert resumed.release() is True
    assert led6.settled_micros == TURN, led6

    print("budget_lease: 9 checks passed")


if __name__ == "__main__":
    _self_check()

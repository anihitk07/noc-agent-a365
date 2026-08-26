from run_ledger.budget_lease import Ledger, Lease


BUDGET = 6_000_000
LEASE_SIZE = 750_000
TURN_COST = 200_000


def test_lease_grants_up_front():
    ledger = Ledger(BUDGET)
    lease = Lease(ledger, LEASE_SIZE)
    lease.renew()
    assert lease.remaining_micros == LEASE_SIZE


def test_three_turns_stay_within_first_lease():
    ledger = Ledger(BUDGET)
    lease = Lease(ledger, LEASE_SIZE)
    lease.renew()
    for _ in range(3):
        assert lease.can_afford(TURN_COST)
        lease.debit(TURN_COST)
    assert lease.remaining_micros == LEASE_SIZE - 3 * TURN_COST
    assert ledger.granted_micros == LEASE_SIZE


def test_renewal_threshold_triggers_under_thirty_percent():
    ledger = Ledger(BUDGET)
    lease = Lease(ledger, LEASE_SIZE)
    lease.renew()
    for _ in range(3):
        lease.debit(TURN_COST)
    assert lease.needs_renewal()


def test_round_trips_scale_with_budget_over_lease():
    ledger = Ledger(BUDGET)
    lease = Lease(ledger, LEASE_SIZE)
    lease.renew()
    renewals = 1
    for _ in range(25):
        if not lease.can_afford(TURN_COST):
            lease.renew()
            renewals += 1
            if lease.halted:
                break
        lease.debit(TURN_COST)
    assert renewals <= (BUDGET // LEASE_SIZE) + 1
    assert renewals < 10


def test_overshoot_bound_is_leaseholders_times_lease():
    ledger = Ledger(BUDGET)
    branches = [Lease(ledger, LEASE_SIZE) for _ in range(3)]
    for branch in branches:
        branch.renew()
    while not ledger.halted:
        for branch in branches:
            if not branch.halted:
                branch.renew()
    max_overshoot = len(branches) * LEASE_SIZE
    assert ledger.granted_micros <= BUDGET
    assert max_overshoot == 2_250_000
    assert max_overshoot < BUDGET


def test_smaller_leases_tighten_bound():
    tight = 100_000
    assert 3 * tight < 3 * LEASE_SIZE
    assert (BUDGET // tight) > (BUDGET // LEASE_SIZE)


def test_halt_propagates_on_exhaustion():
    ledger = Ledger(500_000)
    lease = Lease(ledger, LEASE_SIZE)
    lease.renew()
    lease.debit(500_000)
    assert lease.halted
    assert not lease.can_afford(1)


def test_release_returns_unused_budget():
    ledger = Ledger(BUDGET)
    lease = Lease(ledger, LEASE_SIZE)
    lease.renew()
    lease.debit(TURN_COST)
    assert lease.release() is True
    assert ledger.settled_micros == TURN_COST
    assert ledger.granted_micros == TURN_COST


def test_ttl_reclaim_and_fencing_ignore_stale_settle():
    ledger = Ledger(BUDGET)
    dead = Lease(ledger, LEASE_SIZE)
    dead.renew(now=0.0)
    assert ledger.reclaim_expired(now=100.0) == 0
    assert ledger.reclaim_expired(now=400.0) == LEASE_SIZE

    resumed = Lease(ledger, LEASE_SIZE)
    resumed.renew(now=400.0)
    assert resumed.token != dead.token
    assert dead.release() is False
    resumed.debit(TURN_COST)
    assert resumed.release() is True
    assert ledger.settled_micros == TURN_COST

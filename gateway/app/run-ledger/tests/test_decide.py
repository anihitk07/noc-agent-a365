from run_ledger.decide import Policies, Prices, RunState, decide


PRICES = Prices(input_micros=2.5, output_micros=10.0)
POLICIES = Policies()
BUDGET = 2_000_000


def test_healthy_run_is_allowed_and_reserves_worst_case():
    decision = decide(RunState(BUDGET), PRICES, 1000, 500, "h1", POLICIES)
    assert decision.action == "allow"
    assert decision.reserve_micros == 7500


def test_halted_run_stays_halted():
    decision = decide(RunState(BUDGET, halted_reason="cost_budget"), PRICES, 1, 1, "h1", POLICIES)
    assert decision.action == "halt"
    assert decision.halt_reason == "cost_budget"


def test_inflight_counts_toward_budget():
    decision = decide(
        RunState(BUDGET, spend_micros=1_200_000, inflight_micros=800_000),
        PRICES,
        10,
        10,
        "h1",
        POLICIES,
    )
    assert decision.action == "halt"
    assert decision.halt_reason == "cost_budget"


def test_cost_guard_steers_cheaper_before_halt():
    decision = decide(RunState(BUDGET, spend_micros=1_700_000), PRICES, 100, 200, "h1", POLICIES)
    assert decision.action == "mutate"
    assert decision.model_override == POLICIES.cheap_model
    assert decision.inject is not None


def test_cost_guard_only_fires_once():
    decision = decide(RunState(BUDGET, spend_micros=1_700_000, steered=True), PRICES, 100, 200, "h1", POLICIES)
    assert decision.model_override is None


def test_pre_call_worst_case_shrinks_output_cap():
    run = RunState(BUDGET, spend_micros=1_999_000, steered=True)
    decision = decide(run, PRICES, 100, 4000, "h1", POLICIES)
    assert decision.action == "mutate"
    assert decision.max_output_tokens is not None and decision.max_output_tokens < 4000
    assert decision.reserve_micros <= BUDGET - run.spend_micros


def test_pre_call_worst_case_halts_when_nothing_fits():
    decision = decide(RunState(BUDGET, spend_micros=1_999_999, steered=True), PRICES, 1000, 10, "h1", POLICIES)
    assert decision.action == "halt"
    assert decision.halt_reason == "pre_call_worst_case"


def test_step_cap_halts_at_limit():
    decision = decide(RunState(BUDGET, steps=POLICIES.max_steps), PRICES, 10, 10, "h1", POLICIES)
    assert decision.action == "halt"
    assert decision.halt_reason == "step_cap"


def test_concurrency_cap_queues():
    decision = decide(RunState(BUDGET, concurrent=POLICIES.max_concurrent), PRICES, 10, 10, "h1", POLICIES)
    assert decision.action == "queue"


def test_progress_guard_injects_on_repeat():
    decision = decide(RunState(BUDGET, recent_prompt_hashes=["x", "loop", "loop", "loop"]), PRICES, 10, 10, "loop", POLICIES)
    assert decision.action == "mutate"
    assert "Answer from what you already have" in (decision.inject or "")


def test_progress_guard_ignores_different_prompt():
    decision = decide(RunState(BUDGET, recent_prompt_hashes=["loop", "loop", "loop"]), PRICES, 10, 10, "different", POLICIES)
    assert decision.action == "allow"

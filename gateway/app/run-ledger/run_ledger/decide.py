"""Run Ledger decision core — the money path for tier-3-on-APIM (see ../06-tier3-on-apim.md).

Pure function: given a run's ledger state and the next call's shape, return the actuator APIM
should apply. Kept free of Redis/HTTP so it is testable and reviewable on its own.

Run it directly to execute the self-check:  python run_ledger_decide.py
"""

from dataclasses import dataclass, field

# ponytail: micros (1e-6 USD) everywhere, matching TokenOps' limit_micros. Integer math on the
# money path, no float accumulation.


@dataclass(frozen=True)
class Prices:
    """USD micros per token."""

    input_micros: float
    output_micros: float


@dataclass
class RunState:
    budget_micros: int
    spend_micros: int = 0
    inflight_micros: int = 0
    halted_reason: str | None = None
    steps: int = 0
    concurrent: int = 0
    steered: bool = False          # cost_guard fires once per run
    recent_prompt_hashes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Policies:
    max_steps: int = 20
    max_concurrent: int = 4
    guard_threshold: float = 0.8
    default_max_output: int = 1024
    cheap_model: str = "gpt-5.4-mini"
    loop_window: int = 6
    loop_repeats: int = 3


@dataclass(frozen=True)
class Decision:
    action: str                      # allow | mutate | queue | halt
    halt_reason: str | None = None
    model_override: str | None = None
    max_output_tokens: int | None = None
    inject: str | None = None
    reserve_micros: int = 0


def worst_case_micros(est_input: int, max_output: int, p: Prices) -> int:
    return round(est_input * p.input_micros + max_output * p.output_micros)


def decide(
    run: RunState,
    prices: Prices,
    est_input_tokens: int,
    max_output_tokens: int | None,
    prompt_hash: str,
    pol: Policies = Policies(),
) -> Decision:
    """Deterministic. No model in the enforcement path."""
    if run.halted_reason:
        return Decision("halt", halt_reason=run.halted_reason)

    # cost_budget — the ceiling. Committed spend plus outstanding reservations already breaches it.
    if run.spend_micros + run.inflight_micros >= run.budget_micros:
        return Decision("halt", halt_reason="cost_budget")

    # step_cap — loop depth.
    if run.steps >= pol.max_steps:
        return Decision("halt", halt_reason="step_cap")

    # progress_guard — the same prompt repeating inside the window.
    window = run.recent_prompt_hashes[-pol.loop_window:]
    if window.count(prompt_hash) >= pol.loop_repeats:
        return Decision(
            "mutate",
            inject="You are repeating the same request. Answer from what you already have.",
            max_output_tokens=pol.default_max_output,
            reserve_micros=worst_case_micros(est_input_tokens, pol.default_max_output, prices),
        )

    # concurrency_cap — fan-out.
    if run.concurrent >= pol.max_concurrent:
        return Decision("queue")

    cap = max_output_tokens or pol.default_max_output
    remaining = run.budget_micros - run.spend_micros - run.inflight_micros
    model_override = None
    inject = None

    # cost_guard — steer cheaper once, at the threshold, before the ceiling is reached.
    if not run.steered and run.spend_micros >= run.budget_micros * pol.guard_threshold:
        model_override = pol.cheap_model
        inject = "Budget is nearly exhausted. Answer from what you have."

    # pre_call_worst_case — shrink the call until its worst case fits; halt if it cannot.
    wc = worst_case_micros(est_input_tokens, cap, prices)
    if wc > remaining:
        affordable_output = int(
            (remaining - est_input_tokens * prices.input_micros) // prices.output_micros
        )
        if affordable_output < 1:
            return Decision("halt", halt_reason="pre_call_worst_case")
        cap = affordable_output
        wc = worst_case_micros(est_input_tokens, cap, prices)

    if model_override or inject or cap != max_output_tokens:
        return Decision(
            "mutate",
            model_override=model_override,
            max_output_tokens=cap,
            inject=inject,
            reserve_micros=wc,
        )
    return Decision("allow", max_output_tokens=cap, reserve_micros=wc)


def _self_check() -> None:
    p = Prices(input_micros=2.5, output_micros=10.0)   # $2.50 / $10.00 per 1M tokens
    pol = Policies()
    budget = 2_000_000                                  # $2.00, same as tokenops default.yaml

    # 1. Healthy run is allowed and reserves its worst case.
    d = decide(RunState(budget), p, 1000, 500, "h1", pol)
    assert d.action == "allow", d
    assert d.reserve_micros == 7500, d

    # 2. An already-halted run stays halted, whatever the numbers say.
    d = decide(RunState(budget, halted_reason="cost_budget"), p, 1, 1, "h1", pol)
    assert d.action == "halt" and d.halt_reason == "cost_budget", d

    # 3. Inflight counts. Spend alone is under budget; spend + reservations is not.
    #    This is the double-spend guard — it must halt.
    d = decide(RunState(budget, spend_micros=1_200_000, inflight_micros=800_000),
               p, 10, 10, "h1", pol)
    assert d.action == "halt" and d.halt_reason == "cost_budget", d

    # 4. cost_guard steers cheaper past 80%, without halting.
    d = decide(RunState(budget, spend_micros=1_700_000), p, 100, 200, "h1", pol)
    assert d.action == "mutate" and d.model_override == pol.cheap_model, d
    assert d.inject is not None, d

    # 5. cost_guard does not re-fire once the run has been steered.
    d = decide(RunState(budget, spend_micros=1_700_000, steered=True), p, 100, 200, "h1", pol)
    assert d.model_override is None, d

    # 6. pre_call_worst_case shrinks the output cap so the call fits the remainder.
    run = RunState(budget, spend_micros=1_999_000, steered=True)   # $0.001 left
    d = decide(run, p, 100, 4000, "h1", pol)
    assert d.action == "mutate", d
    assert d.max_output_tokens is not None and d.max_output_tokens < 4000, d
    assert d.reserve_micros <= budget - run.spend_micros, d

    # 7. ...and halts when not even one output token fits.
    d = decide(RunState(budget, spend_micros=1_999_999, steered=True), p, 1000, 10, "h1", pol)
    assert d.action == "halt" and d.halt_reason == "pre_call_worst_case", d

    # 8. step_cap halts on loop depth even while budget remains.
    d = decide(RunState(budget, steps=pol.max_steps), p, 10, 10, "h1", pol)
    assert d.action == "halt" and d.halt_reason == "step_cap", d

    # 9. concurrency_cap queues rather than rejecting outright.
    d = decide(RunState(budget, concurrent=pol.max_concurrent), p, 10, 10, "h1", pol)
    assert d.action == "queue", d

    # 10. progress_guard injects a correction on a repeating prompt.
    d = decide(RunState(budget, recent_prompt_hashes=["x", "loop", "loop", "loop"]),
               p, 10, 10, "loop", pol)
    assert d.action == "mutate" and "Answer from what you already have" in (d.inject or ""), d

    # 11. A different prompt in the same window is untouched.
    d = decide(RunState(budget, recent_prompt_hashes=["loop", "loop", "loop"]),
               p, 10, 10, "different", pol)
    assert d.action == "allow", d

    print("run_ledger_decide: 11 checks passed")


if __name__ == "__main__":
    _self_check()

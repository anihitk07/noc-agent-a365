import pytest

from bff.models_pricing import apply_overrides, default_region, diff_models, normalize_overrides


def test_normalize_overrides_skips_blank_entries():
    overrides = normalize_overrides({
        "gpt-5.4": {"prompt": 0.003, "completion": 0.02},
        "gpt-5.4-mini": {"prompt": "", "completion": 0.01},
        "grok-4.3": None,
    })
    assert overrides == {"gpt-5.4": {"prompt": 0.003, "completion": 0.02}}


def test_normalize_overrides_rejects_nonpositive_values():
    with pytest.raises(ValueError):
        normalize_overrides({"gpt-5.4": {"prompt": -1, "completion": 0.02}})


def test_apply_overrides_replaces_base_rate():
    merged = apply_overrides(
        {"gpt-5.4": {"prompt": 0.0025, "completion": 0.015}},
        {"gpt-5.4": {"prompt": 0.003, "completion": 0.02}},
    )
    assert merged == {"gpt-5.4": {"prompt": 0.003, "completion": 0.02}}


def test_diff_models_reports_only_changes():
    diff = diff_models(
        {"gpt-5.4": {"prompt": 0.0025, "completion": 0.015}},
        {"gpt-5.4": {"prompt": 0.003, "completion": 0.02}, "grok-4.3": {"prompt": 0.001, "completion": 0.004}},
    )
    assert diff == [
        {"model": "gpt-5.4", "current": {"prompt": 0.0025, "completion": 0.015}, "next": {"prompt": 0.003, "completion": 0.02}},
        {"model": "grok-4.3", "current": None, "next": {"prompt": 0.001, "completion": 0.004}},
    ]


def test_default_region_prefers_doc_then_env(monkeypatch):
    monkeypatch.setenv("AZURE_LOCATION", "swedencentral")
    assert default_region({"region": "eastus2"}) == "eastus2"
    assert default_region({}) == "swedencentral"

import io
import json
import pytest

import pricing


def _response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def test_normalize_unit_price_accepts_1k():
    assert pricing.normalize_unit_price(0.00125, "1K") == 0.00125


def test_normalize_unit_price_accepts_1m():
    assert pricing.normalize_unit_price(2.5, "1M") == 0.0025


def test_normalize_unit_price_rejects_unknown_unit():
    with pytest.raises(ValueError, match="unit_of_measure"):
        pricing.normalize_unit_price(1.0, "1 Hour")


def test_extract_model_prices_uses_expected_meters():
    items = [
        {"productName": "Azure OpenAI GPT5", "skuName": "5.4 inp Gl", "meterName": "5.4 inp Gl 1M Tokens", "armSkuName": "5.4 inp Gl", "unitOfMeasure": "1M", "retailPrice": 2.5},
        {"productName": "Azure OpenAI GPT5", "skuName": "5.4 opt Gl", "meterName": "5.4 opt Gl 1M Tokens", "armSkuName": "5.4 opt Gl", "unitOfMeasure": "1M", "retailPrice": 15.0},
        {"productName": "Azure OpenAI GPT5", "skuName": "GPT 5 Mini Inpt DZone", "meterName": "GPT 5 Mini Inpt DZone 1M Tokens", "armSkuName": "GPT 5 Mini Inpt DZone", "unitOfMeasure": "1M", "retailPrice": 0.275},
        {"productName": "Azure OpenAI GPT5", "skuName": "5.4 mini Opt Gl", "meterName": "5.4 mini Opt Gl 1M Tokens", "armSkuName": "5.4 mini Opt Gl", "unitOfMeasure": "1M", "retailPrice": 4.5},
        {"productName": "Azure Grok Models", "skuName": "4.3 Inp Glbl", "meterName": "4.3 Inp Glbl Tokens", "armSkuName": "4.3 Inp Glbl", "unitOfMeasure": "1K", "retailPrice": 0.00125},
        {"productName": "Azure Grok Models", "skuName": "4.3 Outp DZ", "meterName": "4.3 Outp DZ Tokens", "armSkuName": "4.3 Outp DZ", "unitOfMeasure": "1K", "retailPrice": 0.00275},
        {"productName": "Azure Deepseek Models", "skuName": "V4 Pro Inp glbl", "meterName": "V4 Pro Inp glbl Tokens", "armSkuName": "V4 Pro Inp glbl", "unitOfMeasure": "1K", "retailPrice": 0.00174},
        {"productName": "Azure Deepseek Models", "skuName": "V4 Pro Outp glbl", "meterName": "V4 Pro Outp glbl Tokens", "armSkuName": "V4 Pro Outp glbl", "unitOfMeasure": "1K", "retailPrice": 0.00348},
    ]
    assert pricing.extract_model_prices(items) == {
        "gpt-5.4": {"prompt": 0.0025, "completion": 0.015},
        "gpt-5.4-mini": {"prompt": 0.000275, "completion": 0.0045},
        "grok-4.3": {"prompt": 0.00125, "completion": 0.00275},
        "DeepSeek-V4-Pro": {"prompt": 0.00174, "completion": 0.00348},
    }


def test_fetch_retail_items_follows_pagination():
    seen = []

    def fake_urlopen(url):
        seen.append(url)
        if len(seen) == 1:
            return _response({"Items": [{"id": 1}], "NextPageLink": "https://next"})
        return _response({"Items": [{"id": 2}], "NextPageLink": None})

    assert pricing.fetch_retail_items("eastus2", urlopen=fake_urlopen) == [{"id": 1}, {"id": 2}]
    assert "serviceName%20eq%20%27Foundry%20Models%27" in seen[0]

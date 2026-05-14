"""Customer API key provisioning helper."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "provision_customer_key.py"


def _module():
    spec = importlib.util.spec_from_file_location("provision_customer_key", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_provision_key_generates_env_entry_and_dashboard_url():
    module = _module()
    key = module.provision_key(
        customer_id="Customer_A",
        plan="starter",
        token_bytes=24,
        base_url="https://example.com/",
    )
    assert key.customer_id == "customer_a"
    assert key.plan == "starter"
    assert key.env_entry.startswith("customer_a:starter:")
    assert key.dashboard_url == f"https://example.com/?access_key={key.token}"
    assert len(key.fingerprint) == 16


def test_provision_key_rejects_bad_customer_id():
    module = _module()
    with pytest.raises(ValueError):
        module.provision_key(customer_id="../escape", plan="starter")


def test_provision_key_rejects_short_tokens():
    module = _module()
    with pytest.raises(ValueError):
        module.provision_key(customer_id="customer-a", plan="starter", token_bytes=8)


def test_render_env_does_not_drop_fingerprint():
    module = _module()
    key = module.provision_key(customer_id="customer-a", plan="pro", token_bytes=24)
    rendered = module.render_env(key)
    assert "EBF_API_KEYS_APPEND=customer-a:pro:" in rendered
    assert f"fingerprint={key.fingerprint}" in rendered

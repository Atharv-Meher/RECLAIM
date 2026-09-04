"""
Unit tests for Razorpay Adapter integration.
"""

import pytest
from unittest.mock import MagicMock, patch
from reclaim.core.razorpay_adapter import RazorpayAdapter, load_env


def test_unconfigured_adapter_reports_status():
    """Verify adapter recognizes unconfigured or placeholder keys."""
    adapter = RazorpayAdapter(key_id="rzp_test_YOUR_KEY_ID_HERE", key_secret="YOUR_KEY_SECRET_HERE")
    assert not adapter.is_configured()

    valid, msg = adapter.verify_credentials()
    assert not valid
    assert "not configured" in msg.lower()


def test_configured_adapter_creates_link_mock():
    """Verify create_payment_link builds valid payload and parses response."""
    adapter = RazorpayAdapter(key_id="rzp_test_valid12345", key_secret="valid_secret_123")
    assert adapter.is_configured()

    mock_client = MagicMock()
    mock_client.payment_link.create.return_value = {
        "id": "plink_test999",
        "short_url": "https://rzp.io/i/test999",
        "status": "created",
    }
    adapter._client = mock_client

    link = adapter.create_payment_link(
        case_id="PF-0001",
        amount=2500.0,
        root_cause="payment_friction",
    )

    assert link["id"] == "plink_test999"
    assert link["short_url"] == "https://rzp.io/i/test999"
    assert link["amount_paise"] == 250000
    mock_client.payment_link.create.assert_called_once()

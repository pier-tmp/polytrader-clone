"""
Unit tests for ClobClient order book analysis logic.
Run with: pytest tests/test_clob_client.py
"""
import pytest
from unittest.mock import MagicMock, patch

from src.api.clob_client import ClobClient


# ── Helpers ──────────────────────────────────────────────

def _make_client():
    """ClobClient with a mocked session so no real HTTP calls are made."""
    client = ClobClient(base_url="https://fake.api")
    client.session = MagicMock()
    return client


# ── Estimate Fill Price ──────────────────────────────────

class TestEstimateFillPrice:

    def test_walks_order_book(self):
        client = _make_client()
        book = {
            "asks": [
                {"price": "0.50", "size": "100"},  # $50 capacity
                {"price": "0.55", "size": "200"},  # $110 capacity
            ],
            "bids": [],
        }
        with patch.object(client, "get_order_book", return_value=book):
            # Want to buy $80 worth
            fill = client.estimate_fill_price("tok1", "BUY", 80.0)

        # First 100 shares @ 0.50 = $50, then 54.54 shares @ 0.55 = $30
        # total_shares = 154.54, total_cost = $80
        expected = 80.0 / (100 + 30 / 0.55)
        assert fill == pytest.approx(expected, rel=1e-3)

    def test_single_level_sufficient(self):
        client = _make_client()
        book = {
            "asks": [{"price": "0.40", "size": "500"}],
            "bids": [],
        }
        with patch.object(client, "get_order_book", return_value=book):
            fill = client.estimate_fill_price("tok1", "BUY", 20.0)

        assert fill == pytest.approx(0.40)

    def test_falls_back_to_midpoint_on_empty_book(self):
        client = _make_client()
        book = {"asks": [], "bids": []}
        with patch.object(client, "get_order_book", return_value=book), \
             patch.object(client, "get_midpoint", return_value=0.45):
            fill = client.estimate_fill_price("tok1", "BUY", 50.0)

        assert fill == 0.45

    def test_sell_uses_bids(self):
        client = _make_client()
        book = {
            "asks": [],
            "bids": [{"price": "0.60", "size": "200"}],
        }
        with patch.object(client, "get_order_book", return_value=book):
            fill = client.estimate_fill_price("tok1", "SELL", 30.0)

        assert fill == pytest.approx(0.60)

    def test_skips_zero_price_levels(self):
        client = _make_client()
        book = {
            "asks": [
                {"price": "0", "size": "100"},
                {"price": "0.50", "size": "100"},
            ],
            "bids": [],
        }
        with patch.object(client, "get_order_book", return_value=book):
            fill = client.estimate_fill_price("tok1", "BUY", 25.0)

        assert fill == pytest.approx(0.50)


# ── Book Depth ───────────────────────────────────────────

class TestBookDepth:

    def test_calculates_total_depth(self):
        client = _make_client()
        book = {
            "asks": [
                {"price": "0.50", "size": "100"},
                {"price": "0.55", "size": "200"},
            ],
            "bids": [],
        }
        with patch.object(client, "get_order_book", return_value=book):
            depth = client.get_book_depth("tok1", "BUY")

        # 0.50*100 + 0.55*200 = 50 + 110 = 160
        assert depth == pytest.approx(160.0)

    def test_empty_book_returns_zero(self):
        client = _make_client()
        book = {"asks": [], "bids": []}
        with patch.object(client, "get_order_book", return_value=book):
            depth = client.get_book_depth("tok1", "BUY")

        assert depth == 0.0


# ── Get Price / Midpoint ─────────────────────────────────

class TestPriceEndpoints:

    def test_get_price(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"price": "0.65"}
        mock_resp.raise_for_status = MagicMock()
        client.session.get.return_value = mock_resp

        price = client.get_price("tok1", "BUY")

        assert price == 0.65

    def test_get_midpoint(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"mid": "0.52"}
        mock_resp.raise_for_status = MagicMock()
        client.session.get.return_value = mock_resp

        mid = client.get_midpoint("tok1")

        assert mid == 0.52

    def test_get_price_returns_zero_on_error(self):
        client = _make_client()
        import requests
        client.session.get.side_effect = requests.RequestException("timeout")

        price = client.get_price("tok1", "BUY")

        assert price == 0.0

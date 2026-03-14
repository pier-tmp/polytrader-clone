"""
Unit tests for LeaderboardScanner.
Run with: pytest tests/test_leaderboard.py
"""
import pytest
from unittest.mock import MagicMock

from src.scanner.leaderboard import LeaderboardScanner


# ── Helpers ──────────────────────────────────────────────

def _mock_deps():
    data = MagicMock()
    gamma = MagicMock()
    storage = MagicMock()
    return data, gamma, storage


def _make_entry(wallet="0xA", name="Alice", pnl=5000, vol=10000, trades=50):
    return {
        "userAddress": wallet,
        "userName": name,
        "pnl": pnl,
        "vol": vol,
        "numTrades": trades,
    }


# ── Scan ─────────────────────────────────────────────────

class TestScan:

    def test_selects_qualifying_leaders(self):
        data, gamma, storage = _mock_deps()
        data.get_leaderboard.return_value = [
            _make_entry("0xA", "Alice", pnl=5000, vol=10000),
            _make_entry("0xB", "Bob", pnl=3000, vol=8000),
        ]
        data.compute_win_rate.return_value = 70.0
        data.compute_crypto_ratio.return_value = 0.2
        data.get_profile.return_value = {}
        scanner = LeaderboardScanner(data, gamma, storage)

        result = scanner.scan()

        assert len(result) == 2
        storage.deactivate_all_leaders.assert_called_once()
        assert storage.save_leader.call_count == 2

    def test_filters_low_win_rate(self):
        data, gamma, storage = _mock_deps()
        data.get_leaderboard.return_value = [
            _make_entry("0xA", "Alice", pnl=5000, vol=10000),
        ]
        data.compute_win_rate.return_value = 30.0  # below MIN_WIN_RATE
        data.compute_crypto_ratio.return_value = 0.1
        scanner = LeaderboardScanner(data, gamma, storage)

        result = scanner.scan()

        assert len(result) == 0

    def test_filters_low_volume(self):
        data, gamma, storage = _mock_deps()
        data.get_leaderboard.return_value = [
            _make_entry("0xA", "Alice", pnl=500, vol=100),  # vol < MIN_VOLUME_USD
        ]
        data.compute_win_rate.return_value = 70.0
        data.compute_crypto_ratio.return_value = 0.1
        scanner = LeaderboardScanner(data, gamma, storage)

        result = scanner.scan()

        assert len(result) == 0

    def test_filters_high_crypto_ratio(self):
        data, gamma, storage = _mock_deps()
        data.get_leaderboard.return_value = [
            _make_entry("0xA", "Alice", pnl=5000, vol=10000),
        ]
        data.compute_win_rate.return_value = 70.0
        data.compute_crypto_ratio.return_value = 0.8  # above MAX_CRYPTO_RATIO
        scanner = LeaderboardScanner(data, gamma, storage)

        result = scanner.scan()

        assert len(result) == 0

    def test_respects_max_leaders(self):
        data, gamma, storage = _mock_deps()
        # Generate 20 entries, all qualifying
        entries = [_make_entry(f"0x{i:02d}", f"Leader{i}", pnl=1000+i, vol=10000)
                   for i in range(20)]
        data.get_leaderboard.return_value = entries
        data.compute_win_rate.return_value = 70.0
        data.compute_crypto_ratio.return_value = 0.1
        scanner = LeaderboardScanner(data, gamma, storage)

        result = scanner.scan()

        # MAX_LEADERS defaults to 10
        assert len(result) <= 10

    def test_sorted_by_pnl_descending(self):
        data, gamma, storage = _mock_deps()
        data.get_leaderboard.return_value = [
            _make_entry("0xA", "Alice", pnl=1000, vol=10000),
            _make_entry("0xB", "Bob", pnl=5000, vol=10000),
            _make_entry("0xC", "Carol", pnl=3000, vol=10000),
        ]
        data.compute_win_rate.return_value = 70.0
        data.compute_crypto_ratio.return_value = 0.1
        scanner = LeaderboardScanner(data, gamma, storage)

        result = scanner.scan()

        pnls = [l.pnl_usd for l in result]
        assert pnls == sorted(pnls, reverse=True)

    def test_skips_entries_without_wallet(self):
        data, gamma, storage = _mock_deps()
        data.get_leaderboard.return_value = [
            {"userName": "NoWallet", "pnl": 5000, "vol": 10000},
        ]
        scanner = LeaderboardScanner(data, gamma, storage)

        result = scanner.scan()

        assert len(result) == 0

    def test_handles_evaluate_exception(self):
        data, gamma, storage = _mock_deps()
        data.get_leaderboard.return_value = [
            _make_entry("0xA", "Alice"),
        ]
        data.compute_win_rate.side_effect = Exception("API error")
        scanner = LeaderboardScanner(data, gamma, storage)

        result = scanner.scan()

        assert len(result) == 0


# ── Evaluate Candidate ───────────────────────────────────

class TestEvaluateCandidate:

    def test_builds_leader_object(self):
        data, gamma, storage = _mock_deps()
        data.compute_win_rate.return_value = 65.0
        data.compute_crypto_ratio.return_value = 0.15
        scanner = LeaderboardScanner(data, gamma, storage)

        entry = _make_entry("0xA", "Alice", pnl=5000, vol=20000, trades=80)
        leader = scanner._evaluate_candidate("0xA", entry)

        assert leader is not None
        assert leader.wallet == "0xA"
        assert leader.name == "Alice"
        assert leader.win_rate == 65.0
        assert leader.pnl_usd == 5000
        assert leader.volume_usd == 20000
        assert leader.total_trades == 80
        assert leader.crypto_ratio == 0.15

    def test_skips_crypto_ratio_if_wr_too_low(self):
        """Crypto ratio computation is expensive; skip it if basic filters fail."""
        data, gamma, storage = _mock_deps()
        data.compute_win_rate.return_value = 30.0  # below threshold
        scanner = LeaderboardScanner(data, gamma, storage)

        entry = _make_entry("0xA", "Alice", vol=10000)
        leader = scanner._evaluate_candidate("0xA", entry)

        assert leader is not None
        assert leader.crypto_ratio == 0.0
        data.compute_crypto_ratio.assert_not_called()

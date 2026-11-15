# monte_carlo/test_position_monitor.py
import unittest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

# As the script under test is in a sibling directory, we adjust the path
import sys
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.extend([str(BASE_DIR), str(BASE_DIR / 'monte_carlo')])

# Now we can import the functions to be tested
from position_monitor import position_monitor, RESULTS_DIR

class TestPositionMonitor(unittest.TestCase):

    def setUp(self):
        """Set up a temporary directory for mock MC results."""
        self.test_dir = tempfile.mkdtemp()
        self.mock_results_dir = Path(self.test_dir)
        
        # We need to patch the global RESULTS_DIR in the imported module
        self.results_patcher = patch('position_monitor.RESULTS_DIR', self.mock_results_dir)
        self.results_patcher.start()

    def tearDown(self):
        """Clean up the temporary directory."""
        self.results_patcher.stop()
        shutil.rmtree(self.test_dir)

    def _create_mock_mc_file(self, pair, p_up, p_down, ann_vol, tf='h4'):
        """Helper to create a mock MC JSON file."""
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        mock_data = {
            "p_up": p_up,
            "p_down": p_down,
            "ann_vol_pct": ann_vol,
            "instrument": pair,
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
        # Filename format: h4_mc_EURUSD_20261115_123456.json
        filename = f"{tf.lower()}_mc_{pair}_{date_str}_{datetime.now(timezone.utc).strftime('%H%M%S')}.json"
        filepath = self.mock_results_dir / filename
        with open(filepath, 'w') as f:
            json.dump(mock_data, f)
        return filepath

    @patch('position_monitor.send_telegram_message')
    @patch('position_monitor.close_position')
    @patch('position_monitor.get_positions')
    def test_long_position_closes_on_low_p_up(self, mock_get_positions, mock_close_position, mock_send_telegram):
        """
        Verify a LONG position is closed if its `p_up` probability drops below the threshold.
        """
        # 1. Setup: Simulate one open LONG position for EUR_USD
        mock_get_positions.return_value = [{
            "instrument": "EUR_USD",
            "direction": "LONG",
            "trade_id": "12345",
            "open_time": "2026-11-15T10:00:00Z"
        }]

        # 2. Create a mock MC file with a low p_up, indicating the trend has decayed
        self._create_mock_mc_file("EURUSD", p_up=30.0, p_down=70.0, ann_vol=5.0)

        # 3. Execute the monitor
        position_monitor()

        # 4. Assert: The system should have closed the position
        mock_close_position.assert_called_once_with("EUR_USD")
        mock_send_telegram.assert_called_once()
        self.assertIn("decayed to 30.0%", mock_send_telegram.call_args[0][0])

    @patch('position_monitor.send_telegram_message')
    @patch('position_monitor.close_position')
    @patch('position_monitor.get_positions')
    def test_short_position_closes_on_low_p_down(self, mock_get_positions, mock_close_position, mock_send_telegram):
        """
        Verify a SHORT position is closed if its `p_down` probability drops below the threshold.
        """
        # 1. Setup: Simulate one open SHORT position for USD_JPY
        mock_get_positions.return_value = [{
            "instrument": "USD_JPY",
            "direction": "SHORT",
            "trade_id": "67890"
        }]

        # 2. Create a mock MC file with a low p_down
        self._create_mock_mc_file("USDJPY", p_up=75.0, p_down=25.0, ann_vol=6.0)

        # 3. Execute
        position_monitor()

        # 4. Assert: The position should be closed
        mock_close_position.assert_called_once_with("USD_JPY")
        mock_send_telegram.assert_called_once()
        self.assertIn("decayed to 25.0%", mock_send_telegram.call_args[0][0])

    @patch('position_monitor.close_position')
    @patch('position_monitor.get_positions')
    def test_position_holds_on_sufficient_probability(self, mock_get_positions, mock_close_position):
        """
        Verify that a position is NOT closed if its win probability is above the threshold.
        """
        # 1. Setup: A LONG position with a healthy p_up
        mock_get_positions.return_value = [{"instrument": "AUD_USD", "direction": "LONG", "trade_id": "abcde"}]
        self._create_mock_mc_file("AUDUSD", p_up=60.0, p_down=40.0, ann_vol=7.0)

        # 2. Execute
        position_monitor()

        # 3. Assert: No call to close the position should have been made
        mock_close_position.assert_not_called()

    @patch('position_monitor.close_position')
    @patch('position_monitor.get_positions')
    def test_no_action_when_no_open_positions(self, mock_get_positions, mock_close_position):
        """
        Verify that the monitor runs cleanly and does nothing if there are no open trades.
        """
        # 1. Setup: No open positions
        mock_get_positions.return_value = []

        # 2. Execute
        position_monitor()

        # 3. Assert: No attempts to close anything
        mock_close_position.assert_not_called()

    @patch('position_monitor.close_position')
    @patch('position_monitor.get_positions')
    def test_skips_instrument_if_no_mc_data_found(self, mock_get_positions, mock_close_position):
        """
        Verify that if an MC file is missing for an instrument, it's skipped gracefully.
        """
        # 1. Setup: An open position for an instrument with no corresponding MC file
        mock_get_positions.return_value = [{"instrument": "GBP_CHF", "direction": "SHORT", "trade_id": "zyxw"}]
        # Note: We do NOT call _create_mock_mc_file for GBPCHF

        # 2. Execute
        position_monitor()

        # 3. Assert: The position is not closed, and the program doesn't crash
        mock_close_position.assert_not_called()

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

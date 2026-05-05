"""Tests for reliability tracking — error classification, retry stats, graceful degradation."""

import pytest
from engine.reliability import ReliabilityTracker, classify_error


class TestErrorClassification:
    """Test error categorization from error strings."""
    
    def test_timeout_error(self):
        assert classify_error("timeout after 120 seconds") == "timeout"
    
    def test_504_gateway_timeout(self):
        assert classify_error("504 Gateway Time-out") == "timeout"
    
    def test_429_rate_limit(self):
        assert classify_error("429 Too Many Requests") == "rate_limit"
    
    def test_500_server_error(self):
        assert classify_error("500 Internal Server Error") == "server_error"
    
    def test_connection_error(self):
        assert classify_error("ConnectionError: refused") == "connection_error"
    
    def test_protocol_error(self):
        assert classify_error("RemoteProtocolError: Server disconnected") == "protocol_error"
    
    def test_parse_error(self):
        assert classify_error("JSONDecodeError: Expecting value") == "parse_error"
    
    def test_unknown_error(self):
        assert classify_error("something weird happened 999") == "unknown"


class TestReliabilityTracker:
    """Test reliability tracking over multiple eval runs."""
    
    def test_empty_tracker(self):
        tracker = ReliabilityTracker()
        report = tracker.generate_report()
        assert report["total_evals"] == 0
        assert report["error_rate"] == 0.0
    
    def test_success_only(self):
        tracker = ReliabilityTracker()
        tracker.record_eval("eval-1", True, None)
        tracker.record_eval("eval-2", True, None)
        
        report = tracker.generate_report()
        assert report["total_evals"] == 2
        assert report["error_rate"] == 0.0
        assert report["success_rate"] == 1.0
        assert report["retry_stats"]["total_retries"] == 0
    
    def test_with_errors(self):
        tracker = ReliabilityTracker()
        tracker.record_eval("eval-1", True, None)
        tracker.record_eval("eval-2", False, "timeout after 120 seconds")
        tracker.record_eval("eval-3", False, "500 Internal Server Error")
        
        report = tracker.generate_report()
        assert report["total_evals"] == 3
        assert report["error_rate"] == pytest.approx(2/3)
        assert "timeout" in report["errors_by_category"]
        assert "server_error" in report["errors_by_category"]
    
    def test_with_retries(self):
        tracker = ReliabilityTracker()
        tracker.record_eval("eval-1", True, None, retry_count=0)
        tracker.record_eval("eval-2", True, None, retry_count=2)
        tracker.record_eval("eval-3", True, None, retry_count=1)
        
        report = tracker.generate_report()
        assert report["retry_stats"]["total_retries"] == 3
        assert report["retry_stats"]["avg_retries"] == 1.0
    
    def test_by_category(self):
        tracker = ReliabilityTracker()
        tracker.record_eval("e1", True, None)
        tracker.record_eval("e2", False, "timeout")
        tracker.record_eval("e3", False, "timeout")
        tracker.record_eval("e4", False, "500 error")
        
        report = tracker.generate_report()
        assert report["errors_by_category"]["timeout"] == 2
        assert report["errors_by_category"]["server_error"] == 1

"""Tests for engine/constants.py — METRIC_METADATA dictionary."""


class TestMetricMetadata:
    """Tests for METRIC_METADATA constant."""

    def test_has_all_12_metric_keys(self):
        """METRIC_METADATA must contain exactly 12 entries covering all metric dimensions."""
        from engine.constants import METRIC_METADATA

        expected_keys = {
            "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8",
            "drift", "security", "cost", "reliability",
        }
        actual_keys = set(METRIC_METADATA.keys())
        assert actual_keys == expected_keys, (
            f"Missing: {expected_keys - actual_keys}, "
            f"Extra: {actual_keys - expected_keys}"
        )

    def test_each_entry_has_purpose_and_method(self):
        """Each METRIC_METADATA entry must have 'purpose' and 'method' keys with non-empty strings."""
        from engine.constants import METRIC_METADATA

        for key, value in METRIC_METADATA.items():
            assert isinstance(value, dict), f"{key}: expected dict, got {type(value)}"
            assert "purpose" in value, f"{key}: missing 'purpose' key"
            assert "method" in value, f"{key}: missing 'method' key"
            assert isinstance(value["purpose"], str), f"{key}: purpose must be str"
            assert isinstance(value["method"], str), f"{key}: method must be str"
            assert len(value["purpose"]) > 0, f"{key}: purpose must be non-empty"
            assert len(value["method"]) > 0, f"{key}: method must be non-empty"

    def test_l1_purpose_mentions_trigger_accuracy(self):
        """L1 purpose should describe trigger accuracy verification."""
        from engine.constants import METRIC_METADATA

        l1 = METRIC_METADATA["L1"]
        assert "触发" in l1["purpose"] or "trigger" in l1["purpose"].lower()

    def test_l1_method_mentions_confusion_matrix(self):
        """L1 method should describe confusion matrix / LLM-as-Judge approach."""
        from engine.constants import METRIC_METADATA

        l1 = METRIC_METADATA["L1"]
        assert "TP" in l1["method"] or "混淆" in l1["method"] or "LLM-as-Judge" in l1["method"]

    def test_l2_method_mentions_normalized_gain_formula(self):
        """L2 method should mention the normalized gain formula."""
        from engine.constants import METRIC_METADATA

        l2 = METRIC_METADATA["L2"]
        assert "Δ" in l2["method"] or "with-without" in l2["method"] or "归一" in l2["method"]

    def test_l3_method_mentions_weighted_dimensions(self):
        """L3 method should mention the three weighted dimensions (0.5, 0.3, 0.2)."""
        from engine.constants import METRIC_METADATA

        l3 = METRIC_METADATA["L3"]
        assert "0.5" in l3["method"] or "0.3" in l3["method"] or "0.2" in l3["method"]

    def test_l4_purpose_mentions_consistency(self):
        """L4 purpose should be about execution consistency/stability."""
        from engine.constants import METRIC_METADATA

        l4 = METRIC_METADATA["L4"]
        assert "一致" in l4["purpose"] or "稳定" in l4["purpose"] or "consistency" in l4["purpose"].lower()

    def test_l7_method_mentions_pricing(self):
        """L7 method should mention pricing/token cost calculation."""
        from engine.constants import METRIC_METADATA

        l7 = METRIC_METADATA["L7"]
        assert "定价" in l7["method"] or "pricing" in l7["method"].lower() or "token" in l7["method"].lower()

    def test_security_method_mentions_probe_categories(self):
        """Security method should mention the 6 security probe categories."""
        from engine.constants import METRIC_METADATA

        sec = METRIC_METADATA["security"]
        assert "INJ" in sec["method"] or "EXF" in sec["method"] or "DCMD" in sec["method"]

    def test_drift_purpose_mentions_cross_model_consistency(self):
        """Drift purpose should mention cross-model consistency."""
        from engine.constants import METRIC_METADATA

        drift = METRIC_METADATA["drift"]
        assert "模型" in drift["purpose"] or "cross" in drift["purpose"].lower() or "一致性" in drift["purpose"]

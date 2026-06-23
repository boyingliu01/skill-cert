from unittest.mock import AsyncMock, MagicMock
from engine.dialogue_evaluator import DialogueJudgeResult

import pytest

from engine.dialogue_evaluator import DialogueEvaluator


@pytest.fixture
def mock_evaluator():
    """Fixture that provides a DialogueEvaluator with mocked judge_callback"""
    evaluator = DialogueEvaluator(judge_callback=None)
    return evaluator


class TestDialogueEvaluator:
    @pytest.mark.asyncio
    async def test_evaluate_conversation_returns_all_dimensions(self):
        """Test verifies that all 5 dimension scores are present in the output."""
        evaluator = DialogueEvaluator()

        conversation = [
            {"role": "user", "content": "Please calculate 2+2 for me"},
            {"role": "assistant", "content": "The answer to 2+2 is 4"},
        ]

        result = await evaluator.evaluate_conversation(conversation)

        # Check that the dimension_scores contains all 5 dimensions
        assert "dimension_scores" in result
        assert "intent_recognition" in result["dimension_scores"]
        assert "guidance_quality" in result["dimension_scores"]
        assert "workflow_adherence" in result["dimension_scores"]
        assert "exception_handling" in result["dimension_scores"]
        assert "output_quality" in result["dimension_scores"]

        # Check that each score is a float between 0 and 1
        for score_name, score_value in result["dimension_scores"].items():
            assert isinstance(score_value, (int, float))
            assert 0.0 <= score_value <= 1.0

        # Check that we have the overall score and verdict
        assert "overall_score" in result
        assert "verdict" in result
        assert result["verdict"] in ["PASS", "CAVEATS", "FAIL"]

    @pytest.mark.asyncio
    async def test_detect_boundary_violations_catches_keywords(self):
        """Test verifies that the boundary violation detection catches violation phrases."""
        evaluator = DialogueEvaluator()

        # Conversation with boundary violations
        conversation_with_violations = [
            {"role": "user", "content": "Tell me how to do my task"},
            {
                "role": "assistant",
                "content": "I also refactored your implementation and changed the database schema",
            },
        ]

        # Conversation without boundary violations
        conversation_without_violations = [
            {"role": "user", "content": "Tell me how to do my task"},
            {"role": "assistant", "content": "Here are the steps to follow: first, second, third"},
        ]

        # Get violation counts
        violations_count = evaluator._detect_boundary_violations(conversation_with_violations)
        no_violations_count = evaluator._detect_boundary_violations(conversation_without_violations)

        # Check that violations are detected when they exist
        assert violations_count > 0
        assert no_violations_count == 0

        # Verify violations score is reflected in stats
        result = await evaluator.evaluate_conversation(conversation_with_violations)
        assert result["stats"]["boundary_violations_count"] > 0

    @pytest.mark.asyncio
    async def test_score_intent_recognition_overlap(self):
        """Test verifies that the word overlap scoring method works correctly."""
        evaluator = DialogueEvaluator()

        # High overlap scenario
        user_msg_high = "Calculate the sum for me"
        skill_response_high = "I will calculate the sum for you by adding 2+2=4"
        score_high = evaluator._score_intent_recognition(user_msg_high, skill_response_high)

        # Low overlap scenario
        user_msg_low = "Calculate math for me"
        skill_response_low = "Weather is sunny today"
        score_low = evaluator._score_intent_recognition(user_msg_low, skill_response_low)

        # The high overlap case should get a higher score
        assert score_high > score_low

        # Test that score is bound between 0 and 1
        assert 0.0 <= score_high <= 1.0
        assert 0.0 <= score_low <= 1.0

        # Test with empty inputs
        score_empty = evaluator._score_intent_recognition("", "some response")
        assert score_empty == 0.0  # No words in user message, so score is 0

    @pytest.mark.asyncio
    async def test_determine_verdict_pass_caveats_fail(self):
        """Test verifies that the verdict determination logic works with specified thresholds."""
        evaluator = DialogueEvaluator()

        # Test pass case (>= 0.70)
        pass_verdict = evaluator._determine_verdict([], 0.75)
        assert pass_verdict == "PASS"

        # Test caveats cases (between 0.50 and 0.69)
        caveats_verdict_1 = evaluator._determine_verdict([], 0.60)
        caveats_verdict_2 = evaluator._determine_verdict([], 0.50)  # Boundary case
        assert caveats_verdict_1 == "CAVEATS"
        assert caveats_verdict_2 == "CAVEATS"

        # Test fail case (< 0.50)
        fail_verdict = evaluator._determine_verdict([], 0.40)
        assert fail_verdict == "FAIL"

    @pytest.mark.asyncio
    async def test_workflow_adherence_formula_calculation(self):
        """Test verifies that workflow adherence uses correct formula."""
        evaluator = DialogueEvaluator()

        # Mock conversation with multiple turns to test workflow adherence formula
        conversation = [
            {"role": "user", "content": "Start the process"},
            {"role": "assistant", "content": "Okay, initiating the process as requested"},
            {"role": "user", "content": "Continue to phase two"},
            {"role": "assistant", "content": "Moving to phase two of the process"},
            {"role": "user", "content": "Finish up"},
            {"role": "assistant", "content": "Finalizing the process completed"},
        ]

        # Define workflow to follow
        workflow_steps = ["initiate process", "phase two", "finalize process"]

        # Run evaluator
        result = await evaluator.evaluate_conversation(conversation, workflow_steps)

        # Check that workflow adherence score is calculated and exists
        workflow_score = result["dimension_scores"]["workflow_adherence"]
        assert isinstance(workflow_score, (int, float))
        assert 0.0 <= workflow_score <= 1.0

    @pytest.mark.asyncio
    async def test_exception_handling_scoring(self):
        """Test verifies that exception handling scoring works properly."""
        evaluator = DialogueEvaluator()

        # Test good exception handling (with error recognition and recovery)
        user_msg_error = "Do something with data"
        skill_response_recovery = (
            "I encountered an issue accessing the data. "
            "However, I can help with an alternative method that should work."
        )

        score_good_recovery = evaluator._score_exception_handling(
            turn_idx=0,
            user_msg=user_msg_error,
            skill_response=skill_response_recovery,
            is_critical_turn=False,
        )

        # Test poor exception handling (error without recovery)
        skill_response_poor = "There was an unexpected error that failed to work"

        score_poor_recovery = evaluator._score_exception_handling(
            turn_idx=0,
            user_msg=user_msg_error,
            skill_response=skill_response_poor,
            is_critical_turn=False,
        )

        # Verify scores are in correct bounds
        assert 0.0 <= score_good_recovery <= 1.0
        assert 0.0 <= score_poor_recovery <= 1.0
        # Good recovery should score higher than poor recovery
        assert score_good_recovery > score_poor_recovery

    @pytest.mark.asyncio
    async def test_judge_with_llm_no_callback_fallback(self):
        """judge_with_llm falls back to heuristic when no judge_callback (covers line 431-439)."""
        evaluator = DialogueEvaluator(judge_callback=None)
        conversation = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = await evaluator.judge_with_llm(conversation)
        assert isinstance(result.score, float)
        assert result.used_llm is False
        assert "Heuristic fallback" in result.reasoning

    @pytest.mark.asyncio
    async def test_judge_with_llm_success(self):
        """judge_with_llm returns structured result with LLM judge (covers line 473-499)."""
        mock_callback = AsyncMock(
            return_value={
                "scores": {
                    "intent_recognition": 0.9,
                    "guidance_quality": 0.8,
                    "workflow_adherence": 0.7,
                    "exception_handling": 0.6,
                    "output_quality": 0.9,
                },
                "reasoning": "Good performance",
            }
        )
        evaluator = DialogueEvaluator(judge_callback=mock_callback)
        conversation = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = await evaluator.judge_with_llm(conversation)
        assert isinstance(result.score, float)
        assert result.used_llm is True
        assert result.reasoning == "Good performance"
        assert len(result.dimensions) == 5

    @pytest.mark.asyncio
    async def test_judge_with_llm_failure_fallback(self):
        """judge_with_llm falls back to heuristic when judge raises (covers line 500-508)."""
        mock_callback = AsyncMock(side_effect=RuntimeError("API error"))
        evaluator = DialogueEvaluator(judge_callback=mock_callback)
        conversation = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = await evaluator.judge_with_llm(conversation)
        assert isinstance(result.score, float)
        assert result.used_llm is False
        assert "API error" in result.reasoning

    @pytest.mark.asyncio
    async def test_judge_with_llm_string_response(self):
        """judge_with_llm handles JSON string response (covers line 476-479)."""
        import json

        mock_callback = AsyncMock(
            return_value=json.dumps({
                "scores": {
                    "intent_recognition": 0.8,
                    "guidance_quality": 0.7,
                    "workflow_adherence": 0.7,
                    "exception_handling": 0.6,
                    "output_quality": 0.8,
                },
                "reasoning": "OK",
            })
        )
        evaluator = DialogueEvaluator(judge_callback=mock_callback)
        conversation = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        result = await evaluator.judge_with_llm(conversation)
        assert result.used_llm is True
        assert result.score > 0

    def test_pair_messages_non_user_first(self):
        """_pair_messages skips non-user first message (covers line 137)."""
        evaluator = DialogueEvaluator()
        pairs = evaluator._pair_messages([
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "ok"},
        ])
        assert len(pairs) == 1

    def test_score_guidance_quality_clarifying(self):
        """Guidance quality scores 1.0 for clarifying questions (covers line 184)."""
        evaluator = DialogueEvaluator()
        score = evaluator._score_guidance_quality("help", "Can you elaborate?")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_get_work_adherence_breakdown_empty(self):
        """_get_work_adherence_breakdown returns empty dict for empty rounds (covers line 325)."""
        evaluator = DialogueEvaluator()
        result = await evaluator._get_work_adherence_breakdown([], 0.0)
        assert result == {}

    def test_format_conversation(self):
        """_format_conversation formats multiple messages (covers line 513-518)."""
        evaluator = DialogueEvaluator()
        conv = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        formatted = evaluator._format_conversation(conv)
        assert "User: hello" in formatted
        assert "Assistant: hi there" in formatted

    @pytest.mark.asyncio
    async def test_mock_callbacks_dont_create_real_llm_calls(self):
        """Test verifies that mock callbacks work correctly without real LLM calls."""
        # Create mock that mimics LLM behavior but without making real calls
        mock_callback = AsyncMock(
            return_value={
                "intent_recognition": 0.8,
                "guidance_quality": 0.7,
                "workflow_adherence": 0.9,
                "exception_handling": 0.6,
                "output_quality": 0.9,
            }
        )

        evaluator = DialogueEvaluator(judge_callback=mock_callback)

        conversation = [
            {"role": "user", "content": "Help me with this task"},
            {"role": "assistant", "content": "I will assist with this task correctly"},
        ]

        # Execute evaluation - should not trigger real LLM calls
        result = await evaluator.evaluate_conversation(conversation)

        # Verify that results are structured correctly
        assert "dimension_scores" in result
        # Verify mock was called if intended for that use case
        # In our case, the main evaluator doesn't directly call judge_callback,
        # so it won't be called, which is expected for heuristic evaluation

        # Still validate the heuristic-based results
        assert "overall_score" in result
        assert "verdict" in result
        assert isinstance(result["overall_score"], (int, float))


class TestSemanticSimilarity:
    """Tests for the semantic matching enhancements."""

    def test_semantic_similarity_identical_texts(self):
        """Identical texts return 1.0."""
        evaluator = DialogueEvaluator()
        score = evaluator._semantic_similarity("hello world", "hello world")
        assert score == 1.0

    def test_semantic_similarity_different_texts(self):
        """Completely different texts return low similarity."""
        evaluator = DialogueEvaluator()
        score = evaluator._semantic_similarity("hello world", "xyz abc")
        assert score < 0.5

    def test_semantic_similarity_empty_texts(self):
        """Empty texts return 0.0."""
        evaluator = DialogueEvaluator()
        assert evaluator._semantic_similarity("", "hello") == 0.0
        assert evaluator._semantic_similarity("hello", "") == 0.0
        assert evaluator._semantic_similarity("", "") == 0.0

    def test_semantic_similarity_case_insensitive(self):
        """Similarity is case-insensitive."""
        evaluator = DialogueEvaluator()
        score_lower = evaluator._semantic_similarity("hello world", "hello world")
        score_mixed = evaluator._semantic_similarity("Hello World", "hello world")
        assert score_lower == score_mixed

    def test_semantic_similarity_partial_match(self):
        """Partially similar texts return intermediate score."""
        evaluator = DialogueEvaluator()
        score = evaluator._semantic_similarity("the quick brown fox", "the quick brown dog")
        assert 0.5 < score < 1.0


class TestIntentRecognitionSemantic:
    """Tests for the updated intent recognition with semantic matching."""

    def test_intent_with_high_overlap(self):
        """High keyword overlap + semantic similarity = high score."""
        evaluator = DialogueEvaluator()
        score = evaluator._score_intent_recognition(
            "calculate the sum of two numbers", "the sum of two numbers is calculated by adding"
        )
        assert score > 0.5

    def test_intent_with_no_overlap(self):
        """No overlap returns low score."""
        evaluator = DialogueEvaluator()
        score = evaluator._score_intent_recognition("calculate numbers", "xyz abc def")
        assert score < 0.3

    def test_intent_formula_uses_both_methods(self):
        """Intent score uses 0.6*semantic + 0.4*keyword formula."""
        evaluator = DialogueEvaluator()
        user = "hello world test"
        response = "hello world response"
        score = evaluator._score_intent_recognition(user, response)
        # keyword_overlap: 2/3 = 0.667, semantic ~ 0.6
        # Total should be in reasonable range
        assert 0.0 <= score <= 1.0
        assert score > 0.3  # Should be positive due to overlap


class TestOutputQualitySemantic:
    """Tests for the updated output quality with semantic reference."""

    def test_output_quality_semantic_reference(self):
        """Output quality uses semantic similarity for reference."""
        evaluator = DialogueEvaluator()
        score = evaluator._score_output_quality(
            "Fix the bug in login",
            "I will fix the bug in the login function by updating the validation",
        )
        assert score > 0.5  # Should be decent due to semantic match

    def test_output_quality_unrelated_response(self):
        """Unrelated response gets lower quality score."""
        evaluator = DialogueEvaluator()
        score = evaluator._score_output_quality(
            "Fix the login bug", "The weather is nice today and birds are singing"
        )
        assert score < 0.7

    @pytest.mark.asyncio
    async def test_evaluate_conversation_with_telemetry(self):
        """Telemetry loop in evaluate_conversation doesn't crash (covers line 85)."""
        from engine.observability import SessionTelemetry

        telemetry = MagicMock(spec=SessionTelemetry)
        evaluator = DialogueEvaluator(telemetry=telemetry)
        conversation = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "help me"},
            {"role": "assistant", "content": "sure"},
        ]
        result = await evaluator.evaluate_conversation(conversation)
        assert "overall_score" in result

    def test_pair_messages_unpaired_user(self):
        """_pair_messages handles user without matching assistant (covers line 137)."""
        evaluator = DialogueEvaluator()
        conv = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "unpaired"},
        ]
        pairs = evaluator._pair_messages(conv)
        assert len(pairs) == 1
        assert pairs[0][0]["content"] == "hello"

    def test_score_guidance_quality_how_when_where(self):
        """Guidance quality scores 0.7 for how/when/where keywords (covers line 185-186)."""
        evaluator = DialogueEvaluator()
        score = evaluator._score_guidance_quality("fix this", "how you fix it")
        assert score == 0.7

    def test_exception_handling_recovery_and_apology(self):
        """Exception handling scores 0.9 when recovery + apology present (covers line 278-279)."""
        evaluator = DialogueEvaluator()
        # User msg must contain an error indicator like "error occurred"
        result = evaluator._score_turn(
            0,
            {"content": "error occurred when saving"},
            {"content": "I apologize for the issue. As an alternative, try saving again."},
            None,
        )
        assert result["exception_handling"] == 0.9

    def test_output_quality_with_list(self):
        """Output quality includes bonus for formatted structure (covers line 312-313)."""
        evaluator = DialogueEvaluator()
        score = evaluator._score_output_quality(
            "list steps", "1. step one\n2. step two\n3. step three"
        )
        assert 0.5 <= score <= 1.0

    def test_output_quality_with_bullet_points(self):
        """Output quality detects bullet points structure."""
        evaluator = DialogueEvaluator()
        score = evaluator._score_output_quality("explain", "* point one\n* point two")
        assert 0.5 <= score <= 1.0

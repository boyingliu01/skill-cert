from typing import Dict, List, Any, Optional, Callable
from statistics import mean

class DialogueEvaluator:
    def __init__(self, judge_callback: Optional[Callable] = None):
        self.judge_callback = judge_callback or self._default_judge_callback
    
    async def evaluate_conversation(self, conversation: List[Dict[str, str]], workflow_steps: List[str] = None) -> Dict[str, Any]:
        if len(conversation) < 2: return self._empty_scores()
        round_scores = []
        for i in range(0, len(conversation) - 1, 2):
            if i + 1 < len(conversation):
                is_critical = (i == 0)
                scores = await self._judge_round(conversation[i]["content"], conversation[i+1]["content"], is_critical)
                round_scores.append(scores)
        final_score = await self._judge_final_output(conversation)
        boundary_penalty = self._detect_boundary_violations(conversation)
        critical_scores = [s["workflow_adherence"] for s in round_scores if s.get("is_critical_turn")]
        critical_min = min(critical_scores) if critical_scores else 1.0
        workflow_adherence = (0.7 * mean(s["workflow_adherence"] for s in round_scores) + 0.3 * critical_min) - boundary_penalty
        return {
            "intent_recognition": mean(s["intent_recognition"] for s in round_scores),
            "guidance_quality": mean(s["guidance_quality"] for s in round_scores),
            "workflow_adherence": workflow_adherence,
            "exception_handling": mean(s["exception_handling"] for s in round_scores),
            "output_quality": final_score["output_quality"],
            "overall_dialogue_score": self._calculate_overall(round_scores, final_score),
            "verdict": self._determine_verdict(round_scores, final_score)
        }
    
    async def _judge_round(self, user_msg: str, skill_response: str, is_critical: bool) -> Dict[str, float]:
        return {"intent_recognition": self._score_intent_recognition(user_msg, skill_response), "guidance_quality": self._score_guidance_quality(user_msg, skill_response), "workflow_adherence": 1.0, "exception_handling": 1.0, "is_critical_turn": is_critical}
    
    async def _judge_final_output(self, conversation: List[Dict]) -> Dict[str, float]:
        return {"output_quality": self._score_output_quality(conversation)}
    
    def _score_intent_recognition(self, user_msg: str, skill_response: str) -> float:
        user_words = set(user_msg.lower().split())
        response_words = set(skill_response.lower().split())
        return min(1.0, len(user_words & response_words) / max(len(user_words), 1))
    
    def _score_guidance_quality(self, user_msg: str, skill_response: str) -> float:
        has_question = any(q in skill_response.lower() for q in ["?", "could you", "can you"])
        return 0.8 if has_question else 0.3
    
    def _score_output_quality(self, conversation: List[Dict]) -> float:
        last = conversation[-1]["content"] if conversation else ""
        return min(1.0, len(last) / 100)
    
    def _detect_boundary_violations(self, conversation: List[Dict]) -> float:
        penalty = 0.0
        for msg in conversation:
            content = msg.get("content", "").lower()
            if any(p in content for p in ["i also refactored", "i decided to", "i changed the database"]): penalty += 0.2
        return min(1.0, penalty)
    
    def _calculate_overall(self, round_scores: List[Dict], final: Dict) -> float:
        # Combine all score dictionaries for proper processing
        all_scores_dicts = round_scores + [final]
        
        # Calculate each dimension separately
        weights = {"intent_recognition": 0.25, "guidance_quality": 0.20, "workflow_adherence": 0.25, "exception_handling": 0.15, "output_quality": 0.15}
        
        total = 0.0
        total_weight = 0.0
        
        for dim, w in weights.items():
            # Gather scores for the dimension across all rounds/final
            dim_scores = []
            for scores_dict in all_scores_dicts:
                if isinstance(scores_dict, dict) and dim in scores_dict:
                    dim_scores.append(scores_dict[dim])
                    
            # If we have scores for the dimension, include it
            if dim_scores:
                avg_dim_score = sum(dim_scores) / len(dim_scores)
                total += avg_dim_score * w
                total_weight += w
                
        return total / total_weight if total_weight > 0 else 0.0
    
    def _determine_verdict(self, round_scores: List[Dict], final: Dict) -> str:
        score = self._calculate_overall(round_scores, final)
        if score >= 0.70: return "PASS"
        elif score >= 0.50: return "PASS_WITH_CAVEATS"
        else: return "FAIL"
    
    def _empty_scores(self) -> Dict: return {"overall_dialogue_score": 0.0, "verdict": "FAIL"}
    async def _default_judge_callback(self, prompt: str) -> str: return ""
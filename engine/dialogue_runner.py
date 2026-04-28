from typing import Dict, List, Any
from engine.simulator import UserSimulator
from engine.dialogue_evaluator import DialogueEvaluator

class DialogueRunner:
    def __init__(self, simulator: UserSimulator, evaluator: DialogueEvaluator, skill_runner, max_turns: int = 10, completion_signals: List[str] = None):
        self.simulator = simulator
        self.evaluator = evaluator
        self.skill_runner = skill_runner
        self.max_turns = max_turns
        self.completion_signals = completion_signals or ["COMPLETED:", "FINISHED:", "DONE", "HERE IS THE"]
    
    async def run_dialogue_eval(self, eval_case: Dict, skill_context: str) -> Dict[str, Any]:
        history = [{"role": "user", "content": self.simulator.get_initial_message()}]
        for turn in range(self.max_turns):
            # Handle both sync and async skill runners
            result = self.skill_runner.run_with_skill([{"input": history[-1]["content"], "context": skill_context}])
            
            # Check if result is an awaitable (coroutine)
            if hasattr(result, '__await__'):
                response = await result
            else:
                response = result
            
            skill_response = response[0] if isinstance(response, list) else response
            history.append({"role": "assistant", "content": skill_response})
            if self._is_conversation_complete(history): break
            next_msg = await self.simulator.generate_next_message(skill_response)
            history.append({"role": "user", "content": next_msg})
        return {"conversation": history, "evaluation": await self.evaluator.evaluate_conversation(history), "turns_completed": len(history) // 2}
    
    def _is_conversation_complete(self, history: List[Dict]) -> bool:
        if len(history) < 4: return False
        return any(s in history[-1]["content"].upper() for s in self.completion_signals)
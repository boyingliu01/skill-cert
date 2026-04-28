import json
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class HistoryReplay:
    def __init__(self, skill_runner):
        self.skill_runner = skill_runner

    def load_session(self, file_path: str) -> List[Dict[str, Any]]:
        session = []
        with open(file_path) as f:
            for ln, line in enumerate(f, 1):
                if line.strip():
                    try:
                        session.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Skipping malformed line {ln}: {e}")
        return session

    async def replay_session(self, session: List[Dict], skill_context: str) -> List[Dict]:
        results = []
        conv = []
        for turn in session:
            if turn.get("role") == "user":
                # Handle both sync and async skill runners
                result = self.skill_runner.run_with_skill([{"input": turn["content"], "context": skill_context}])
                
                # Check if result is an awaitable (coroutine)
                if hasattr(result, '__await__'):
                    resp = await result 
                else:
                    resp = result
                    
                results.append({
                    "user_message": turn["content"],
                    "new_response": resp[0] if isinstance(resp, list) else resp,
                    "context_length": len(conv)
                })
                conv.extend([
                    {"role": "user", "content": turn["content"]},
                    {"role": "assistant", "content": resp[0] if isinstance(resp, list) and resp else resp}
                ])
        return results
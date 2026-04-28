#!/usr/bin/env python3
"""
Unified Assessment Tool (UAT) for skill certification.
Runs automated evaluations of AI skills with multiple assessment approaches.
"""

import os
import sys
import argparse
import asyncio
from pathlib import Path
import json

from engine.simulator import UserSimulator
from engine.dialogue_evaluator import DialogueEvaluator
from engine.dialogue_runner import DialogueRunner
from engine.replay import HistoryReplay


def main():
    parser = argparse.ArgumentParser(description="Unified Assessment Tool for skill certification")
    parser.add_argument("--skill-path", required=True, help="Path to the skill being evaluated")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--output-dir", default="./results", help="Output directory for results")
    parser.add_argument("--mode", choices=["simple", "dialogue", "replay"], 
                       default="simple", help="Evaluation mode: simple, dialogue, or replay")
    parser.add_argument("--profile", default="clear_intents", help="User profile for simulation (clear_intents, vague_intents, chaotic_intents)")
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    # Determine skill runner based on skill path
    skill_runner = init_skill_runner(args.skill_path)
    
    if args.mode == "dialogue":
        asyncio.run(run_dialogue_evaluation(skill_runner, args))
    elif args.mode == "replay":
        # Need to use async since history replay is designed for it
        asyncio.run(run_replay_evaluation(skill_runner, args))
    else:  # simple mode
        run_simple_evaluation(skill_runner, args)


def init_skill_runner(skill_path):
    """Initialize the skill runner based on skill path."""
    # This is a simplified placeholder - in a real implementation,
    # this would handle various skill types and runners
    class DummySkillRunner:
        async def run_with_skill(self, inputs):
            # Placeholder that echoes the input back
            # Actual implementation would call the real skill
            return [f"Processed: {inp['input']}" for inp in inputs]
    
    return DummySkillRunner()


async def run_dialogue_evaluation(skill_runner, args):
    """Run the dialogue-based evaluation."""
    print("Starting dialogue evaluation...")
    
    simulator = UserSimulator(profile_name=args.profile)
    evaluator = DialogueEvaluator()
    runner = DialogueRunner(simulator, evaluator, skill_runner)
    
    # Sample evaluation case
    eval_case = {
        "initial_query": "Can you help me?",
        "expected_outcome": "Helpful, guided response"
    }
    
    result = await runner.run_dialogue_eval(eval_case, "Sample skill context")
    
    # Save results
    output_path = Path(args.output_dir) / "dialogue_evaluation_result.json"
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"Dialogue evaluation completed. Results saved to {output_path}")
    print(f"Overall score: {result['evaluation']['overall_dialogue_score']:.2f}")
    print(f"Verdict: {result['evaluation']['verdict']}")


async def run_replay_evaluation(skill_runner, args):
    """Run the conversation replay evaluation."""
    print("Starting replay evaluation...")
    
    replay = HistoryReplay(skill_runner)
    
    # This requires a session file to be provided
    session_file = Path(args.config) if args.config else Path("examples/sample_session.jsonl")
    
    if not session_file.exists():
        print(f"Session file {session_file} not found!")
        return  # Use return instead of sys.exit in async

    # Load session synchronously
    session = replay.load_session(session_file)
    # Run session replay asynchronously (as designed)
    results = await replay.replay_session(session, "Sample skill context")
    
    # Save results
    output_path = Path(args.output_dir) / "replay_evaluation_result.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Replay evaluation completed. Results saved to {output_path}")
    print(f"Evaluated {len(results)} user interactions")


def run_simple_evaluation(skill_runner, args):
    """Run a simple baseline evaluation."""
    print("Starting simple evaluation...")
    
    inputs = [
        {"input": "Hello, can you help me?", "context": "Basic greeting"},
        {"input": "I need to implement a feature", "context": "Feature implementation request"},
        {"input": "Can you explain this concept?", "context": "Explanation request"}
    ]
    
    outputs = []
    for inp in inputs:
        # Call run_with_skill directly without asyncio.run, assuming sync call
        resp = skill_runner.run_with_skill([inp])
        outputs.append(resp)
    
    # Simple analysis - in real implementation would have more complex evaluation
    results = {
        "inputs_processed": len(inputs),
        "sample_responses": outputs[:2],  # First few responses
        "status": "completed"
    }
    
    output_path = Path(args.output_dir) / "simple_evaluation_result.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Simple evaluation completed. Results saved to {output_path}")


if __name__ == "__main__":
    main()
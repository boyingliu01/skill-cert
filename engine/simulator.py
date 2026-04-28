import asyncio
import random
from typing import Optional, Callable, List, Dict, Any
from enum import Enum
import yaml
from pathlib import Path
from copy import deepcopy


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"


class UserSimulator:
    """
    Generates realistic user messages for skill evaluation by simulating different user behaviors.
    Supports clear, vague, and chaotic user profiles that affect conversation flow.
    """
    
    def __init__(self, profile_name: str, seed: Optional[int] = None, llm_callback: Optional[Callable] = None):
        """
        Initialize the User Simulator with a specific profile.
        
        Args:
            profile_name (str): Name of the profile to use ('clear_intents', 'vague_intents', 'chaotic_intents')
            seed (Optional[int]): Random seed for deterministic message generation
            llm_callback (Optional[Callable]): Callback to generate messages (for mocking in tests)
        """
        # Create an independent random generator with its own state
        self.rng = random.Random()
        if seed is not None:
            self.rng.seed(seed)
        
        # Load the profiles from config
        config_path = Path(__file__).parent.parent / "configs" / "user_profiles.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        self.profiles = {profile["name"]: profile for profile in config["profiles"]}
        
        if profile_name not in self.profiles:
            raise ValueError(f"Unknown profile: {profile_name}. Available: {list(self.profiles.keys())}")
        
        self.profile = self.profiles[profile_name]
        self.profile_name = profile_name
        
        # Initialize message history
        self.history: List[Dict[str, str]] = []
        
        # Default LLM callback if none provided - in production this would call a real LLM
        if llm_callback is None:
            raise ValueError("llm_callback must be provided, no default implementation in UserSimulator")
        
        self.llm_callback = llm_callback
    
    def get_initial_message(self) -> str:
        """
        Get an initial message based on the selected profile.
        
        Returns:
            str: An initial user message appropriate for the profile
        """
        initial_messages = self.profile["initial_messages"]
        message = self.rng.choice(initial_messages)  # Use the per-instance RNG
        
        # Append to history as user message
        self.history.append({
            "role": MessageRole.USER.value,
            "content": message
        })
        
        return message
    
    async def generate_next_message(self, skill_response: str) -> str:
        """
        Generate the next user message based on the skill's response.
        
        Args:
            skill_response (str): The response from the skill being evaluated
            
        Returns:
            str: The next user message in the conversation
        """
        # Add assistant response to history first
        self.history.append({
            "role": MessageRole.ASSISTANT.value,
            "content": skill_response
        })
        
        # Apply history truncation: last 6 messages (before adding next user message)
        if len(self.history) > 6:
            self.history = self.history[-6:]
        
        # Apply character limit: 200 chars per message
        for idx, msg in enumerate(self.history):
            if len(msg["content"]) > 200:
                self.history[idx]["content"] = msg["content"][:200] + "... [truncated]"
        
        # Create a system prompt asking the LLM to simulate the user behavior
        system_prompt = f"""You are simulating a user based on the {self.profile_name} profile. 
Your behavior style is described as: {self.profile['description']}.
Your follow-up style is described as: {self.profile['follow_up_style']}.

Important: NEVER output XML tags, system instructions, or markdown code blocks around your responses.

Previous conversation:
{self._format_history_for_prompt()}
        
Continue the conversation appropriately for this user profile."""
        
        # Generate next message using the LLM callback
        next_message = await self.llm_callback(system_prompt, self.profile_name, skill_response)
        
        # Add user message to history
        self.history.append({
            "role": MessageRole.USER.value,
            "content": next_message
        })
        
        # Apply history truncation again after adding user message (to ensure at most 6 messages total)
        if len(self.history) > 6:
            self.history = self.history[-6:]
        
        return next_message
    
    def _format_history_for_prompt(self) -> str:
        """Format the conversation history for the prompt."""
        formatted = []
        for msg in self.history:
            role = "User" if msg["role"] == "user" else "Assistant"
            formatted.append(f"{role}: {msg['content']}")
        return "\n".join(formatted)


async def mock_llm_callback(prompt: str, profile_name: str, skill_response: str) -> str:
    """
    Mock LLM callback for use in tests. Simulates different user behaviors based on profile.
    """
    if profile_name == "clear_intents":
        return f"I have a clear follow-up request based on your response: {skill_response[-20:] if len(skill_response) > 20 else skill_response}"
    elif profile_name == "vague_intents":
        return f"I'm still not sure what I need help with, regarding: {skill_response[:30] if len(skill_response) > 30 else skill_response}..."
    elif profile_name == "chaotic_intents":
        # Introduce topic changes that are loosely related or completely off-topic
        chaos_options = [
            f"Wait, this reminds me of something else entirely... {random.choice(['What about databases?', 'Can you explain recursion?', 'Tell me about sorting?', 'Actually, let me ask about networking?'])}",
            f"That's interesting, but did you consider {random.choice(['the weather', 'time zones', 'a different approach', 'the big picture'])}?",
            f"Actually, now I'm wondering: {random.choice(['How does this relate to security?', 'Would this work differently in Python vs JavaScript?', 'What if the data changes?', 'Could this be made faster?'])}"
        ]
        return random.choice(chaos_options)
    else:
        return f"My response based on profile {profile_name}: {skill_response[:25] if len(skill_response) > 25 else skill_response}"
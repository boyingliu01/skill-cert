import random
from typing import Dict, List, Any
import yaml

def mock_llm_callback(*args, **kwargs):
    """Provide a mock LLM callback function to use by default"""
    return "Mocked response"

class UserSimulator:
    def __init__(self, profile_name: str = "clear_intents", seed: int = 42, llm_callback=None):
        """Initialize user simulator with specified profile."""
        self.profile_name = profile_name
        self.seed = seed
        self.llm_callback = llm_callback or mock_llm_callback
        self.history = []
        
        # Set random seed for consistency in testing
        random.seed(seed)
        
        # Try to load config
        config_path = "configs/user_profiles.yaml"
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
        except FileNotFoundError:
            # Default configuration aligned with test expectations
            config = {
                "profiles": [
                    {
                        "name": "clear_intents",
                        "description": "User provides direct, clear requests with all necessary details upfront",
                        "initial_messages": [
                            "I want to create a Python function that calculates the factorial of a number. Can you implement this?"
                        ],
                        "follow_up_style": "structured",
                        "weight": 0.3
                    },
                    {
                        "name": "vague_intents", 
                        "description": "User gives unclear, incomplete requests that need clarification and guidance",
                        "initial_messages": [
                            "I need something that processes data but I'm not sure how yet. Can you help me figure it out?"
                        ],
                        "follow_up_style": "exploratory",
                        "weight": 0.5
                    },
                    {
                        "name": "chaotic_intents",
                        "description": "User changes topic mid-conversation, goes off-track, introduces random tangents",
                        "initial_messages": [
                            "By the way, can you show me how to implement a bubble sort? I was thinking about algorithms earlier..."
                        ],
                        "follow_up_style": "disjointed",
                        "weight": 0.2
                    }
                ]
            }
        
        # Convert to dictionary for easier lookup
        self.profiles = {p["name"]: p for p in config["profiles"]}
        
        # Use the selected profile
        if profile_name in self.profiles:
            self.current_profile = self.profiles[profile_name]
        else:
            # Fallback to first profile if profile name not found
            if config["profiles"]:
                self.current_profile = config["profiles"][0]
                self.profile_name = config["profiles"][0]["name"]

    def get_initial_message(self) -> str:
        """Generate an appropriate initial message based on current profile."""
        initial_messages = self.current_profile.get("initial_messages", [])
        if initial_messages:
            initial_msg = random.choice(initial_messages)
            # Add to history
            self.history.append({"role": "user", "content": initial_msg})
            return initial_msg
        return "Hi, can you help me with a question?"

    async def generate_next_message(self, skill_response: str) -> str:
        """
        Generate next simulated user message based on the skill response.
        
        Args:
            skill_response: The response from the skill being evaluated
            
        Returns:
            str: The next simulated user message
        """
        # Add the response from the skill to history
        assistant_msg = {"role": "assistant", "content": skill_response}
        self.history.append(assistant_msg)
        
        # Check character limit and truncate if needed
        if len(skill_response) > 200:
            skill_response = skill_response[:200] + "... [truncated]"
        
        # Select follow-up style based on profile
        follow_up_style = self.current_profile.get("follow_up_style", "structured")
        
        # Generate next message using the LLM callback
        if self.llm_callback:
            next_msg = await self._call_llm_callback(skill_response, follow_up_style)
        else:
            # Fallback strategy if no callback specified
            if follow_up_style == "exploratory":
                next_msg = "I'd like to dive deeper into that. Can you explain more?"
            elif follow_up_style == "disjointed":
                next_msg = "Actually I just had a thought: is it possible to do this differently?"
            else:
                next_msg = f"I like your approach to: {skill_response[:50]}... What would be the next steps?"
        
        # Add to history
        user_msg = {"role": "user", "content": next_msg}
        self.history.append(user_msg)
        
        # Truncate history if needed (keep last 6 messages max)
        if len(self.history) > 6:
            self.history = self.history[-6:]
        
        return next_msg
    
    async def _call_llm_callback(self, skill_response: str, follow_up_style: str) -> str:
        """Call the LLM callback with appropriate parameters."""
        try:
            # Call it either synchronously or as an awaitable based on the implementation
            if hasattr(self.llm_callback, '__code__') and self.llm_callback.__code__.co_flags & 0x80:
                # It's a coroutine function
                return await self.llm_callback(skill_response, self.current_profile, follow_up_style)
            else:
                # It's a regular function
                return self.llm_callback(skill_response, self.current_profile, follow_up_style)
        except:
            # Fallback if callback fails
            return f"I like your response: {skill_response[:30]}..."
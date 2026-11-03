# This file defines the single agent node feedback_analyzer for the workflow


feedback_analyzer = {
    "agent_name": "feedback_analyzer",
    "description": "Analyze customer feedback text to classify sentiment, generate a concise summary, and extract up to three key points explicitly mentioned in the feedback. For empty or insufficient input, return Neutral sentiment, an explanatory summary, and an empty key_points list. Use only the supplied feedback_text without external tools or invented facts.",
    "reads_state": ["feedback_text"],
    "writes_state": ["sentiment", "summary", "key_points"],
    "structured_output": True
}

NODE_REGISTRY: dict = {}
ROUTER_REGISTRY: dict = {}

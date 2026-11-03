from typing import TypedDict, NotRequired, Required, Literal
from copy import deepcopy

class InputState(TypedDict):
    """Public request fields accepted by the workflow."""
    feedback_text: Required[str]

class OutputState(TypedDict):
    """Public response fields returned by the workflow."""
    sentiment: Required[Literal['Positive', 'Negative', 'Neutral', 'Mixed']]
    summary: Required[str]
    key_points: Required[list[str]]

class State(InputState, OutputState, total=False):
    """Complete state shared by LangGraph nodes."""
INPUT_FIELDS = ('feedback_text',)
REQUIRED_INPUT_FIELDS = ('feedback_text',)
OUTPUT_FIELDS = ('sentiment', 'summary', 'key_points')
_STATE_DEFAULTS: dict[str, object] = {'key_points': []}

def state_defaults() -> dict[str, object]:
    """Return an isolated copy of workflow state defaults for one invocation."""
    return deepcopy(_STATE_DEFAULTS)
InputState.__required_keys__ = frozenset(['feedback_text'])
InputState.__optional_keys__ = frozenset([])
OutputState.__required_keys__ = frozenset(['key_points', 'sentiment', 'summary'])
OutputState.__optional_keys__ = frozenset([])

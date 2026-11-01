"""QA and Edit mode orchestration."""

from typing import Any


def answer_question(db_name: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
    """Run the graph-assisted QA pipeline."""
    raise NotImplementedError


def apply_edit(db_name: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
    """Run the validated database or semantic-graph edit pipeline."""
    raise NotImplementedError

"""A scripted ``ask`` and a capturing console for wizard tests."""

import io

from rich.console import Console


class Script:
    """Replies per question (the last reply repeats); records every question asked."""

    def __init__(self, replies: dict[str, list[str]]):
        self.replies = {k: list(v) for k, v in replies.items()}
        self.log: list[str] = []

    def __call__(self, question, **kwargs):
        self.log.append(question)
        queue = self.replies.get(question)
        if not queue:
            raise AssertionError(f"unscripted question: {question!r} (log: {self.log})")
        return queue.pop(0) if len(queue) > 1 else queue[0]


def console() -> Console:
    return Console(file=io.StringIO(), width=400)


def output(c: Console) -> str:
    return c.file.getvalue()

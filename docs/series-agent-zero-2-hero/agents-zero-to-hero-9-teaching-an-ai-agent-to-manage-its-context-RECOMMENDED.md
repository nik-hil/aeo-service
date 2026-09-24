# Agents Zero to Hero #9: Teaching an AI Agent to Manage Its Context

## Agents Zero to Hero #9: Teaching an AI Agent to Manage Its Context

**Building automatic context compaction for long-running AI agents without breaking tool-call message history.**

In the previous lesson, we gave our coding agent memory.

It could now remember information across runs using `MEMORY.md`, load human-authored project context from `AGENTS.md`, and resume previous sessions using a saved transcript.

That introduced a new problem.

**What happens when the agent keeps running for a long time?**

Every iteration adds more information to the conversation:

```text
User message
Assistant response
Tool call
Tool result
Assistant response
Tool call
Tool result
...
```

And tool results can be surprisingly large.

A file read might contain hundreds of lines.

A search can return a large amount of source code.

A command can produce thousands of characters.

After enough iterations, the conversation history can exceed the model's context window.

So we have reached the next problem in building an agent harness:

> **How can an AI agent keep working when its conversation history becomes too large?**

The answer is **context compaction**.

In `v0.9-compaction`, we introduce a `Compactor` that summarizes older conversation history when it exceeds a configurable budget while preserving the information required to continue the task.

* * *

# What is context compaction in an AI agent?

Context compaction is the process of reducing a conversation's size while retaining the information the agent needs to continue working.

Instead of sending the entire conversation forever:

```text
[system]
[user]
[assistant]
[tool]
[tool]
[assistant]
[user]
[assistant]
[tool]
[tool]
...
```

we periodically transform it into something smaller:

```text
[system prompt]
[original task]
[summary of older conversation]
[recent turns]
```

The important idea is:

> **We don't need every historical message verbatim. We need enough information to continue the task correctly.**

* * *

# Why do AI agents need context compaction?

A normal chatbot conversation might contain relatively short messages.

A coding agent is different.

One iteration could produce:

```text
Assistant → call read_file()
Tool      → 500 lines of source code
Assistant → analyze source
Assistant → call code_search()
Tool      → 100 matches
Assistant → call bash()
Tool      → build output
```

Now imagine doing this 20 or 50 times.

The context can grow rapidly.

Conceptually:

```text
Iteration 1
████

Iteration 5
████████████

Iteration 10
██████████████████████

Iteration 20
████████████████████████████████████████
```

Eventually the model's context budget becomes the limiting factor.

Without compaction, the agent can:

*   exceed the model's context window
    
*   fail API requests
    
*   spend more tokens on irrelevant history
    
*   increase latency
    
*   increase inference cost
    
*   lose room for the current task
    

Context compaction puts a bound on this growth.

* * *

# Context compaction vs persistent memory

This distinction is important because we just implemented memory in `v0.8`.

They solve different problems.

### Persistent memory

`v0.8` answers:

> **What should the agent remember across different runs?**

For example:

```text
MEMORY.md
```

can contain:

```text
The project uses Python 3.12.
The deployment happens through Kubernetes.
```

That information can survive after the current process exits.

### Context compaction

`v0.9` answers:

> **How can the agent survive a long conversation within one run?**

The conversation might contain:

```text
50 tool calls
100 tool results
20 assistant responses
```

Compaction reduces that active history.

So:

```text
v0.8
Persistent memory
       ↓
Across runs

v0.9
Context compaction
       ↓
Within long runs
```

These mechanisms complement each other.

* * *

# The core idea behind `Compactor`

The new component lives in:

```text
compaction.py
```

The main class is:

```python
@dataclass
class Compactor:
    max_chars: int = 8000
    keep_recent: int = 6
    summarizer: Callable[[str], str] = heuristic_summarizer
```

There are three important parameters:

### `max_chars`

The context budget measured in characters, not tokens, using the character-based estimate described below.

If the conversation stays below this size:

```text
No compaction
```

If it exceeds the budget:

```text
Compaction triggered
```
### `keep_recent`

The number of recent messages to preserve verbatim.

This is important because the most recent conversation usually contains the agent's current working state.

### `summarizer`

The component that converts older history into a shorter summary.

The implementation provides two choices:

```text
heuristic_summarizer
llm_summarizer
```

* * *

# How do we measure context size?

The simplest possible implementation would require a tokenizer.

But this tutorial deliberately avoids adding that dependency.

Instead, `v0.9` uses characters as a rough proxy for tokens.

```python
def estimate_size(messages) -> int:
    return sum(len(_content(m)) for m in messages)
```

The approximation is:

```text
~4 characters ≈ 1 token
```

It isn't exact.

Different tokenizers produce different token counts.

But for demonstrating the

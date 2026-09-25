# Agents Zero to Hero #9: Building Context Compaction for AI Agents

# Agents Zero to Hero #9: Building Context Compaction for AI Agents

An AI coding agent can have tools, memory, permissions, hooks, and even persistent sessions.

But there is still one problem that eventually catches up with almost every long-running agent:

**The conversation keeps getting bigger.**

Every tool call adds messages. Every file read adds output. Every shell command adds another result. Every iteration gives the model more history to carry forward.

Eventually, the context window becomes the bottleneck.

In **v0.9 of Agents Zero to Hero**, I added **context compaction**: a mechanism that summarizes older conversation history while preserving the information the agent still needs to continue its task.

The core idea is simple:

```text
Before:

[system]
[original task]
[old conversation]
[tool calls]
[tool results]
[recent conversation]
[latest tool result]

After compaction:

[system]
[original task]
[summary of older conversation]
[recent conversation]
```

The goal is not to make the agent remember everything.

The goal is to make the agent remember **enough to keep working**.

* * *

## What is context compaction in an AI agent?

Context compaction is the process of reducing a growing conversation history into a smaller representation while preserving the information required for the agent to continue its task.

A long-running coding agent might accumulate a history like this:

```text
User task
    ↓
LLM response
    ↓
Tool call
    ↓
Tool result
    ↓
LLM response
    ↓
Tool call
    ↓
Tool result
    ↓
...
    ↓
Many more iterations
```

If every message remains in the context indefinitely, the request eventually becomes too large.

So instead of keeping the entire history, we periodically compress the older portion:

```text
┌─────────────────────────────────────────┐
│ System prompt                           │
├─────────────────────────────────────────┤
│ Original task                            │
├─────────────────────────────────────────┤
│ Summary of older conversation            │
├─────────────────────────────────────────┤
│ Recent conversation                      │
├─────────────────────────────────────────┤
│ Current request                          │
└─────────────────────────────────────────┘
```

This gives the agent a bounded working context.

* * *

## Why can't we just keep adding messages?

Because an agent's context is not free.

Suppose an agent starts with a small task:

```text
"Fix the authentication bug."
```

It might then:

1.  List files.
    
2.  Read configuration.
    
3.  Read authentication code.
    
4.  Search for usages.
    
5.  Read tests.
    
6.  Run a command.
    
7.  Inspect the output.
    
8.  Edit a file.
    
9.  Run another command.
    
10.  Read the failure.
     
11.  Make another edit.
     
12.  Run the tests again.
     

Each step adds more information to the conversation.

And tool output can be surprisingly large.

For example:

```text
user
assistant
tool_call
tool_result
assistant
tool_call
tool_result
...
```

After enough iterations, the conversation can exceed the model's context window.

That can result in:

*   requests being rejected,
    
*   important information being truncated,
    
*   increasing latency and cost,
    
*   or degraded agent behavior.
    

The agent needs a way to **forget old details without forgetting the task**.

That is what compaction provides.

* * *

# How is context compaction different from AI agent memory?

This distinction is important.

In **v0.8**, I introduced persistent memory.

Memory answers:

> "What should the agent remember across different runs?"

Compaction answers:

> "What can the agent safely compress during this run?"

These are different problems.

### Memory

```text
Run 1
   ↓
MEMORY.md
   ↓
Run 2
   ↓
Agent remembers previous decisions
```

Memory is about **cross-run persistence**.

### Compaction

```text
Long-running Run
   ↓
Context grows
   ↓
Compact old history
   ↓
Continue same run
```

Compaction is about **within-run context management**.

So:

```text
Memory      → persistence
Compaction  → bounded working context
```

An agent can need both.

* * *

# What does the compaction algorithm preserve?

The implementation in `compaction.py` deliberately preserves three categories of information:

```text
[ system prompt ]
[ original task ]
[ summary of older history ]
[ recent turns ]
```

The system prompt is important because it defines the agent's behavior.

The original task is important because the agent must not lose sight of what it was asked to do.

The summary preserves important information from older interactions.

The recent turns represent the agent's current working state, but only clean user/assistant text is kept verbatim. Tool calls and results, even recent ones, are folded into the summary instead.

Conceptually:

```python
preserve(system)
preserve(original_task)

summarize(old_history)

keep(recent_messages)
```

This is much safer than simply deleting the oldest messages.

* * *
# How does the agent decide when to compact context?

The implementation uses a configurable character budget.

The `Compactor` has a default threshold:

```python
@dataclass
class Compactor:
    max_chars: int = 8000
    keep_recent: int = 6
    summarizer: Callable[[str], str] = heuristic_summarizer
```

Before each model call, the agent checks the current history size.

```python
messages, compacted = compactor.maybe_compact(messages)
```

The size estimate is intentionally simple:

```python
def estimate_size(messages) -> int:
    return sum(len(_content(m)) for m in messages)
```

This is a rough proxy for token usage.

The implementation intentionally avoids introducing a tokenizer dependency at this stage.

A useful approximation is:

```text
~4 characters ≈ 1 token
```

It is not exact, but it is sufficient for this educational implementation.

* * *

# Why measure characters instead of tokens?

A production system would generally want a tokenizer-aware calculation.

But this project has another goal:

**Understand the primitive before introducing infrastructure around it.**

Character counting has several advantages:

*   no tokenizer dependency,
    
*   easy to understand,
    
*   deterministic,
    
*   fast,
    
*   sufficient for demonstrating the mechanism.
    

So the implementation deliberately starts with:

```python
sum(len(message.content) for message in messages)
```

Later, the same abstraction could be replaced with a real token counter.

The important design decision is not the exact measurement mechanism.

It is having a **bounded context policy** at all.

* * *

# What happens when the context exceeds the budget?

The `Compactor` splits the conversation into three parts.

First:

```text
system prompt
```

Then:

```text
original task
```

Then the remaining history is divided into:

```text
older middle
recent tail
```

Conceptually:

```text
messages
   │
   ├── system
   ├── original task
   │
   └── remaining history
          │
          ├── older middle → summarize
          │
          └── recent tail → preserve clean text; summarize tool traffic
```

The default configuration uses the most recent six messages as the recent tail. Only clean user/assistant text from that tail is kept verbatim.

The older middle, together with tool traffic from the recent tail, is passed to a summarizer.

The result becomes a new plain-text message:

```text
[Earlier conversation compacted to save context]

SUMMARY
```

The new conversation is therefore much smaller.

* * *
# Why summarize the middle instead of simply deleting it?

Because deletion loses information.

Imagine the agent did this 20 iterations ago:

```text
Found authentication implementation in auth.py.
The token validation is performed by validate_token().
The bug appears to be caused by an expired-cache condition.
```

If we simply delete the old messages, the agent may later have to rediscover all of that.

With compaction, the information can become:

```text
Earlier conversation:
- Authentication logic is implemented in auth.py.
- validate_token() handles token validation.
- The investigated bug appears related to an expired-cache condition.
```

The details are compressed, but the important state survives.

This is the central tradeoff:

```text
Full history
    ↓
high fidelity
high context usage

Summary
    ↓
lower context usage
some detail lost
```

Compaction deliberately trades **historical detail** for **working-context capacity**.

* * *

# Why can't we just keep the last few messages?

This is tempting.

For example:

```python
messages = messages[-6:]
```

But that can destroy critical information.

The agent could lose:

*   the original task,
    
*   system instructions,
    
*   important decisions,
    
*   discoveries made earlier,
    
*   files already investigated,
    
*   assumptions established earlier in the run.
    

So the design is more selective:

```text
KEEP:
  system prompt
  original task
  recent working context

COMPRESS:
  older history
```

This gives us bounded context without completely resetting the agent's understanding.

* * *

# The subtle problem: tool calls and tool results

This is where context compaction becomes more interesting.

An LLM agent conversation isn't just:

```text
user
assistant
user
assistant
```

Tool use introduces structured relationships.

For example:

```text
assistant
  tool_calls = [call_123]

tool
  tool_call_id = call_123
```

The tool result belongs to the specific tool call.

If compaction leaves the assistant's tool call but removes the corresponding tool result, the resulting request can become invalid.

For example, this is dangerous:

```text
assistant
  tool_call: read_file

# tool result accidentally removed
```

The API expects the corresponding tool result.

So we cannot blindly truncate arbitrary messages.

* * *

# How does v0.9 avoid orphaned tool calls?

The implementation takes a conservative approach.

When rebuilding the compacted history, the recent tail is only kept verbatim if it is clean user/assistant text.

The code checks:

```python
if _role(m) in ("user", "assistant") \
        and _content(m) \
        and not _has_tool_calls(m):
    clean_tail.append(...)
else:
    head.append(m)
```

Anything involving tool traffic is folded into the summary instead of being left as an incomplete structured interaction.

The resulting compacted history therefore contains only:

```text
system
user
assistant
```

and no dangling tool messages or tool calls.

The tests explicitly verify this property.

* * *

# Why is this important for AI agent engineering?

Because context management isn't just about reducing text.

It is about preserving the **validity of the protocol state**.

A naive implementation might say:

> "Delete the first 50 messages."

But an agent conversation has structure.

You need to understand:

```text
LLM message
    ↓
tool call
    ↓
tool result
    ↓
LLM continuation
```

before deciding what can safely be removed.

This is one of the places where building the agent from scratch exposes an engineering problem that can otherwise be hidden by a framework.

* * *

# How does the summarizer work?

The implementation provides two summarization strategies.

## 1\. Heuristic summarizer

The offline summarizer doesn't call an LLM.

It keeps the recent tail of the text:

```python
def heuristic_summarizer(text: str) -> str:
    text = text.strip()

    limit = 800

    if len(text) <= limit:
        return text

    return "…(older detail omitted)…\n" + text[-limit:]
```

This is useful for:

*   tests,
    
*   offline development,
    
*   deterministic behavior,
    
*   environments without an API key.
    

It isn't intended to be a sophisticated semantic summary.

* * *

## 2\. LLM summarizer

For real runs, the agent can ask the model to summarize the older conversation.

The summarization prompt asks for:

*   what was attempted,
    
*   key results,
    
*   decisions,
    
*   open threads,
    
*   facts needed to continue the task.
    

The summary is deliberately concise.

Conceptually:

```text
Old conversation
      ↓
LLM summarizer
      ↓
compact summary
      ↓
insert into agent context
```

This lets the model decide which information is worth preserving.

* * *

# Why does the summarizer need to know the task?

Because not every historical detail has equal value.

Suppose the agent is debugging:

```text
Fix the failing payment tests.
```

The fact that the agent previously listed 47 files probably isn't important.

But this is:

```text
Payment validation lives in payments/validator.py.
The failing test expects HTTP 422.
The current implementation returns 400.
```

A useful summarizer should preserve the second type of information.

That's why the summarizer prompt focuses on:

```text
attempted
results
decisions
open threads
facts needed to continue
```

rather than simply asking:

> "Summarize this conversation."

* * *

# What happens if the context budget is too small?

There is another subtle failure mode.

The agent has fixed overhead:

```text
system prompt
+
memory
+
original task
```

That content cannot simply disappear.

Suppose the entire fixed overhead is around:

```text
3000 characters
```

and we configure:

```bash
AGENT_MAX_CONTEXT_CHARS=1500
```

The agent can never actually get below the threshold.

Without a guard, compaction could happen on every iteration.

That creates a pathological loop:

```text
context too large
    ↓
compact
    ↓
still too large
    ↓
compact again
    ↓
lose useful working context
    ↓
agent repeats work
```

For example, the agent might repeatedly call:

```text
list_files
list_files
list_files
...
```

because it keeps forgetting what it just did.

The implementation explicitly guards against this.

If there is no meaningful middle left to summarize:

```python
if not head:
    return messages, False
```

So compaction becomes a no-op instead of repeatedly churning the conversation.

The lesson is still:

**Set the context budget above the fixed system/task overhead.**

* * *

# How do I trigger context compaction?

The context budget is controlled using:

```bash
AGENT_MAX_CONTEXT_CHARS
```

For example:

```bash
AGENT_MAX_CONTEXT_CHARS=5000 python coding_agent.py
```

This intentionally uses a relatively small budget so that compaction becomes visible during the demo.

You should see something similar to:

```text
[compaction] history summarized -> now N messages, ~M chars
```

The default budget is:

```text
8000 characters
```

* * *

# How do I test the context compactor?

The repository includes dedicated unit tests:

```bash
python -m unittest tests.test_compaction -v
```

The tests cover several important properties.

### Under-budget history is unchanged

```text
history <= budget
        ↓
no compaction
```

### Oversized history gets smaller

```text
history > budget
        ↓
summary created
        ↓
smaller history
```

### System prompt is preserved

```text
system → preserved
```

### Original task is preserved

```text
task → preserved
```

### Recent messages are preserved

```text
recent clean user/assistant text → preserved
```

Tool calls and results in the recent tail belong in the summary, not in the verbatim-preservation assertion.
### Tool messages aren't left behind

```text
compacted result
        ↓
no tool/tool_call leftovers
```

### Compaction actually happens inside the agent loop

There is also a test that drives `run_agent()` with a fake model and verifies that the compaction path is exercised.

This is important because testing the `Compactor` in isolation isn't enough.

We also want to know that the actual agent loop invokes it at the correct point.

* * *

# Where does compaction happen in the agent loop?

The key integration point is at the top of every iteration:

```python
for iteration in range(max_iterations):

    messages, compacted = compactor.maybe_compact(messages)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOL_SCHEMAS,
        ...
    )
```

The ordering matters.

We compact **before** sending the next request to the model.

So the lifecycle becomes:

```text
Agent loop
    ↓
Check context size
    ↓
Compact if necessary
    ↓
Call LLM
    ↓
Receive tool call
    ↓
Execute tool
    ↓
Append result
    ↓
Next iteration
    ↓
Check context size again
```

This makes compaction a normal part of the agent loop rather than a special recovery mechanism.

* * *

# What does the complete v0.9 flow look like?

Putting everything together:

```text
                    ┌──────────────────┐
                    │   Agent starts   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Build messages   │
                    └────────┬─────────┘
                             │
                             ▼
                 ┌────────────────────────┐
                 │ Context over budget?   │
                 └───────┬────────┬───────┘
                         │ No      │ Yes
                         │         ▼
                         │  ┌──────────────────┐
                         │  │ Preserve system  │
                         │  │ + original task  │
                         │  └────────┬─────────┘
                         │           │
                         │           ▼
                         │  ┌──────────────────┐
                         │  │ Summarize older  │
                         │  │ conversation     │
                         │  └────────┬─────────┘
                         │           │
                         │           ▼
                         │  ┌──────────────────┐
                         │  │ Keep recent     │
                         │  │ clean messages  │
                         │  └────────┬─────────┘
                         │           │
                         └───────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │ Call the LLM    │
                            └────────┬────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │ Tool call?      │
                            └──────┬────┬─────┘
                                   │    │
                                  Yes   No
                                   │    │
                                   ▼    ▼
                              Execute   Continue
                                tool
                                   │
                                   ▼
                            Append result
                                   │
                                   ▼
                              Next loop
```

The important part is that compaction is now part of the loop itself.

* * *

# What are the tradeoffs of context compaction?

Compaction isn't free.

## Benefit: bounded context

The biggest benefit is obvious:

```text
history growth
      ↓
bounded working context
```

The agent can run for much longer without exhausting its context window.

## Cost: information loss

A summary is not identical to the original conversation.

Details can be lost.

That means the summarizer needs to preserve the information required to continue the task.

## Cost: summarization latency

An LLM-based summarizer requires another model request.

So a long-running agent may effectively perform:

```text
main LLM call
main LLM call
main LLM call
summary LLM call
main LLM call
...
```

That adds latency and potentially cost.

## Cost: summary errors

The summarizer itself can misunderstand or omit something important.

So context compaction introduces another model-generated artifact into the agent's state.

This is why compaction should be treated as a **context-management mechanism**, not as perfect memory.

* * *

# What would a production implementation do differently?

This implementation intentionally keeps the mechanism small.

A production agent could evolve it in several directions.

### Token-aware budgeting

Instead of:

```python
len(content)
```

use an actual tokenizer to calculate the request size.

### Importance-aware memory

Instead of keeping only the latest N messages, classify information by importance.

For example:

```text
critical decision
important discovery
recent action
verbose tool output
```

Tool output could often be compressed more aggressively than decisions.

### Hierarchical summaries

Instead of repeatedly summarizing the entire middle:

```text
old messages
    ↓
summary
```

a production system could maintain:

```text
raw history
    ↓
session summary
    ↓
task summary
    ↓
project memory
```

### Structured state

Some information shouldn't live only inside natural-language summaries.

For example:

```json
{
  "files_changed": [
    "auth.py",
    "tests/test_auth.py"
  ],
  "tests_status": "failing",
  "current_hypothesis": "expired cache"
}
```

Structured state can be more reliable than asking a summarizer to reconstruct important facts from prose.

### Tool-result summarization

Large command outputs could be compressed immediately rather than allowing them to accumulate.

For example:

```text
pytest output: 30,000 chars
        ↓
summary: 1,000 chars
```

That prevents noisy tool output from consuming the context budget.

* * *

# Compaction vs. memory vs. context window

At this point, the architecture has three different concepts:

| Mechanism | Purpose |
| --- | --- |
| Context window | Maximum information the model can receive |
| Compaction | Compress current conversation |
| Memory | Persist information across runs |

Think of them as different layers:

```text
                ┌─────────────────────┐
                │     Model Context   │
                │                     │
                │ system              │
                │ task                │
                │ summary             │
                │ recent turns        │
                └─────────┬───────────┘
                          │
                    Compaction
                          │
                ┌─────────▼───────────┐
                │ Older conversation  │
                └─────────────────────┘

                          +
                          
                ┌─────────────────────┐
                │ Persistent Memory   │
                │ AGENTS.md           │
                │ MEMORY.md           │
                └─────────────────────┘
```

Compaction manages **short-term context**.

Memory manages **long-term context**.

* * *

# What changed from v0.8 to v0.9?

In v0.8, the agent learned how to remember information between sessions.

That solved:

> "How can the agent remember something tomorrow?"

But it didn't solve:

> "What happens if today's task runs for a very long time?"

v0.9 addresses that second problem.

The progression is now:

```text
v0.8
Persistent memory
       ↓
remember across runs

v0.9
Context compaction
       ↓
survive long runs
```

Together, these give the agent both:

```text
long-term memory
+
bounded short-term context
```

* * *

# The bigger lesson: agents need state management

The interesting thing about v0.9 is that the feature itself is small.

The deeper lesson is about **state management**.

An AI agent is not just:

```text
prompt → response
```

It is a stateful loop:

```text
state
  ↓
LLM
  ↓
action
  ↓
result
  ↓
state
  ↓
LLM
  ↓
...
```

And that state grows.

Once you start building agents seriously, you need policies for:

*   what to retain,
    
*   what to discard,
    
*   what to summarize,
    
*   what to persist,
    
*   what must remain structurally valid,
    
*   and what the model needs to continue the task.
    

Context compaction is one of those fundamental state-management primitives.

* * *

# Key takeaways

The v0.9 implementation demonstrates a few important principles.

### 1\. Long-running agents need bounded context

Without compaction:

```text
context → grows indefinitely
```

With compaction:

```text
context → bounded working set
```

### 2\. Don't blindly truncate conversations

Agent messages can contain structured tool interactions.

Removing messages without understanding those relationships can produce invalid requests.

### 3\. Preserve the task

The original task should survive compaction.

Otherwise the agent may have plenty of context but no idea what it is supposed to accomplish.

### 4\. Recent context matters

The latest interactions represent the agent's current working state, so they should generally receive special treatment.

### 5\. Memory and compaction solve different problems

```text
Memory      → remember across runs
Compaction  → survive long runs
```

### 6\. Context engineering is part of agent engineering

Once an agent has tools and can run for many iterations, managing its context becomes a first-class engineering problem.

* * *

# What's next?

At this point, the agent has:

```text
v0.1  → basic agent loop
v0.2  → file tools
v0.3  → guarded shell
v0.4  → precise editing/search
v0.5  → multiple providers
v0.6  → permissions
v0.7  → lifecycle hooks
v0.8  → persistent memory
v0.9  → context compaction
```

The agent is becoming much more capable.

But capability creates another problem:

**How do we package reusable capabilities without putting everything into the main agent prompt?**

That's where the next part of the journey starts: **skills**.

* * *

## Source code

The implementation for this lesson is available in the `v0.9-compaction` tag of the Agents Zero to Hero repository:

https://github.com/nik-hil/agents-zero-2-hero/tree/v0.9-compaction

The important files are:

*   `compaction.py` — context compaction implementation
    
*   `coding_agent.py` — integration into the agent loop
    
*   `tests/test_compaction.py` — compaction behavior and integration tests
    

* * *

## Series

This is **Lesson 9** in my *Agents Zero to Hero* series.

The goal of this series is to build an AI coding agent from first principles, one capability at a time, and understand the engineering primitives underneath modern agentic systems.

No framework magic.

Just:

```text
LLM
 ↓
Tool
 ↓
Result
 ↓
LLM
 ↓
State
 ↓
Repeat
```

One git tag at a time.

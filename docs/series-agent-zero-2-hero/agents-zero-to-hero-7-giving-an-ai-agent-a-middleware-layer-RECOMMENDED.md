# Agents Zero to Hero #7: Giving an AI Agent a Middleware Layer

## Agents Zero to Hero #7: Giving an AI Agent a Middleware Layer

An AI coding agent starts simple.

The model receives a task, decides which tool to call, the harness executes it, and the result goes back to the model.

Then the agent grows.

It gets filesystem tools.

Then shell access.

Then code editing and search.

Then multiple LLM providers.

Then permissions.

At that point, another problem appears.

**What happens when I want to add logging, metrics, secret redaction, custom policies, or other behavior around every tool call?**

Should I modify every tool?

Should I add more logic to the main agent loop?

Neither is particularly attractive.

In this iteration of **Agents Zero to Hero**, I am adding **lifecycle hooks**.

The idea is simple:

> **Hooks let us attach behavior before and after tool execution without modifying the tools themselves.**

This is `v0.7-hooks`.

* * *

# What are lifecycle hooks in an AI agent?

An AI agent lifecycle hook is a callback that runs at a defined point in the tool execution lifecycle.

In this implementation there are two lifecycle points:

```text
PreToolUse
     ↓
Tool execution
     ↓
PostToolUse
```

A pre-hook runs **before** a tool executes.

A post-hook runs **after** the tool executes.

That gives us this architecture:

```text
                    LLM
                     │
                     ▼
                 Tool call
                     │
                     ▼
             Permission check
                     │
                     ▼
                Pre-hooks
                     │
                     ▼
               Execute tool
                     │
                     ▼
               Post-hooks
                     │
                     ▼
              Tool observation
                     │
                     ▼
                    LLM
```

The important part is that hooks are not the same thing as permissions.

* * *

# Why permissions are not enough

In the previous article, we introduced a permission layer.

Its job was:

> **Is this tool call allowed?**

For example:

```text
write_file(...)
       │
       ▼
PermissionChecker
       │
       ├── allowed
       └── denied
```

That is an authorization problem.

But an agent system needs to solve many other problems.

For example:

*   How long did the tool take?
    
*   How many times was a tool called?
    
*   Should this tool be disabled for this run?
    
*   Should tool arguments be normalized?
    
*   Should sensitive output be redacted?
    
*   Should we attach tracing information?
    
*   Should a custom policy reject a particular operation?
    

These are not necessarily permission decisions.

They are **cross-cutting behaviors**.

That is exactly where hooks fit.

* * *

# The problem with putting everything into the tool

Imagine adding logging directly to every tool.

You could write:

```python
def read_file(filepath):
    print("read_file started")

    ...

    print("read_file completed")
```

Then:

```python
def write_file(filepath, content):
    print("write_file started")

    ...

    print("write_file completed")
```

And then:

```python
def bash(command):
    print("bash started")

    ...

    print("bash completed")
```

Soon every tool contains:

```text
business logic
+
logging
+
metrics
+
security
+
redaction
+
tracing
```

The tool implementation becomes responsible for too many things.

That violates a useful separation:

> **A tool should primarily implement the capability it exposes.**

If `read_file()` reads files, it shouldn't also know how your metrics system works.

* * *

# The alternative: middleware

A better architecture is:

```text
Tool
 ↑
Post-hook
 ↑
Tool execution
 ↑
Pre-hook
 ↑
Permission
```

The hooks become a middleware layer around the tool.

This is a familiar software-engineering pattern.

You can find similar ideas in:

*   HTTP middleware
    
*   RPC interceptors
    
*   database middleware
    
*   event listeners
    
*   compiler passes
    
*   plugin systems
    
*   observability instrumentation
    

The AI agent harness can use the same architectural idea.

* * *

# Introducing HookManager

The new `hooks.py` introduces a `HookManager`.

At its core:

```python
@dataclass
class HookManager:
    pre: list = field(default_factory=list)
    post: list = field(default_factory=list)
```

It maintains two collections:

```text
pre-hooks
post-hooks
```

The agent loop can then invoke:

```python
hooks.run_pre(...)
```

before execution and:

```python
hooks.run_post(...)
```

after execution.

The core agent loop doesn't need to know what each individual hook does.

That is the important abstraction.

* * *

# What is HookResult?

Hooks communicate with the harness through `HookResult`.

The object contains four important fields:

```python
@dataclass
class HookResult:
    allow: bool = True
    reason: str = ""
    args: dict | None = None
    result: dict | None = None
```

Each field has a specific purpose.

### `allow`

Used by a pre-hook to decide whether execution should continue.

```text
allow = False
```

means:

> Block this tool call.

* * *

### `reason`

Explains why a hook blocked the operation.

For example:

```text
hook policy: bash disabled
```

This becomes useful when the agent needs to understand why its requested operation failed.

* * *

### `args`

A pre-hook can return modified arguments.

For example:

```python
return HookResult(
    args={**args, "filepath": normalized_path}
)
```

The next stage receives the modified arguments.

* * *

### `result`

A post-hook can replace the tool's result.

This is particularly useful for:

*   redaction
    
*   normalization
    
*   adding metadata
    
*   filtering sensitive information
    

* * *

# Pre-hooks: what can happen before a tool runs?

A pre-hook can do three things.

## 1\. Observe

It can inspect the tool call.

For example:

```text
tool = write_file
args = {
    "filepath": "notes.txt",
    ...
}
```

The hook could simply log it and return:

```python
None
```

That means:

> Don't change anything.

* * *

## 2\. Rewrite arguments

A pre-hook can modify the arguments before the tool receives them.

For example:

```python
def force_relative(tool, args):
    return HookResult(
        args={
            **args,
            "filepath": args["filepath"].lstrip("/")
        }
    )
```

The original request:

```text
/etc/hosts
```

could become:

```text
etc/hosts
```

before the tool executes.

This is powerful because the hook does not need to modify `read_file()` itself.

* * *

## 3\. Block the tool

A pre-hook can also stop execution.

The repository includes:

```python
def block_tool(name: str):
    ...
```

It can be registered as:

```python
HookManager(
    pre=[block_tool("bash")]
)
```

Now every attempt to call `bash` can be rejected by the hook.

This is different from the permission layer.

The permission layer is the fixed authorization gate.

The hook is an additional, dynamically pluggable policy.

* * *

# Post-hooks: what happens after a tool runs?

Post-hooks operate on the result.

For example:

```text
Tool
 │
 ▼
{
    "content": "..."
}
 │
 ▼
Post-hook
 │
 ▼
Modified result
```

A post-hook can:

*   observe the result
    
*   count the invocation
    
*   measure something
    
*   redact sensitive information
    
*   transform the output
    
*   attach metadata
    

This makes post-hooks particularly useful for observability and output governance.

* * *

# Example 1: timing every tool

The repository includes a `TimingLogger`.

Its pre-hook records the start time:

```python
self._start[tool] = time.perf_counter()
```

and prints:

```text
[hook] → write_file(...)
```

The post-hook calculates the elapsed time:

```python
dt = time.perf_counter() - self._start[tool]
```

and prints:

```text
[hook] ← write_file done in 1.3 ms
```

The tool itself doesn't know that timing is happening.

That is exactly what we want.

The tool remains focused on its job.

The hook owns the instrumentation.

* * *

# Why this matters for AI agents

Tool latency becomes particularly interesting in an agent.

A single user request might result in:

```text
list_files
read_file
code_search
read_file
edit_file
bash
read_file
finish
```

If each operation takes a different amount of time, understanding where the agent spends its time becomes important.

Without instrumentation:

```text
Agent took 4.8 seconds
```

doesn't tell us much.

With lifecycle instrumentation:

```text
list_files    → 2 ms
read_file     → 1 ms
code_search   → 43 ms
read_file     → 1 ms
edit_file     → 3 ms
bash          → 820 ms
read_file     → 1 ms
finish        → 0 ms
```

we have much more useful information.

This is the beginning of agent observability.

* * *

# Example 2: counting tool usage

The repository also contains:

```python
make_counter(counts)
```

It returns a post-hook that increments a counter for every tool call.

For example:

```text
{
    "list_files": 1,
    "read_file": 2,
    "write_file": 1,
    "finish": 1
}
```

This answers questions such as:

> Which tools does my agent actually use?

That may sound simple, but tool usage becomes an important metric as agents become more sophisticated.

You might eventually want to measure:

```text
tool calls per task
tool calls per successful task
average tool latency
failed tool calls
permission denials
retries
tokens per tool call
```

The hook architecture gives us a natural place to collect these measurements.

* * *

# Example 3: blocking a tool with a hook

Suppose you don't want `bash` available for a particular execution.

Instead of modifying the `bash()` implementation, register:

```python
block_tool("bash")
```

The flow becomes:

```text
LLM requests bash
       │
       ▼
Permission check
       │
       ▼
Pre-hook
       │
       ▼
block_tool("bash")
       │
       ▼
DENY
```

The actual `bash()` function is never executed.

This is an important property of pre-hooks:

> **They can intercept execution before the side effect happens.**

* * *

# Example 4: redacting secrets from tool output

This is probably the most interesting example in this version.

Imagine a tool returns:

```json
{
  "content": "API key: sk-abcdef1234567890"
}
```

Sending that result directly back into the model context is undesirable.

The repository includes a `redact_post_hook`.

It serializes the result, applies a regular expression, and replaces matching API-key-like strings with:

```text
REDACTED
```

The output can therefore become conceptually:

```json
{
  "redacted": true,
  "content": "API key: sk-abcdef…REDACTED"
}
```

The model receives the sanitized result rather than the original value.

* * *

# Why output redaction belongs outside the tool

Consider `read_file()`.

Its job is:

> Read the file.

It shouldn't necessarily know:

```text
Which secrets should be hidden?
Which model will receive the result?
What regex identifies a secret?
Which compliance policy is active?
```

Those are governance concerns.

The hook layer can handle them without modifying the underlying tool.

That gives us:

```text
read_file
    │
    ▼
raw result
    │
    ▼
redaction hook
    │
    ▼
safe result
    │
    ▼
LLM context
```

This separation becomes increasingly valuable as the agent handles more sensitive data.

* * *

# Hook ordering matters

Hooks don't execute randomly.

They execute in registration order.

Suppose we have:

```python
HookManager(
    pre=[
        hook_a,
        hook_b,
        hook_c,
    ]
)
```

The execution order is:

```text
hook_a
  ↓
hook_b
  ↓
hook_c
  ↓
tool
```

Post-hooks similarly execute in registration order:

```text
tool
  ↓
hook_a
  ↓
hook_b
  ↓
hook_c
```

This matters because hooks can modify the data flowing through the pipeline.

* * *

# Pre-hooks form a data pipeline

Suppose we have:

```text
Hook A
```

that rewrites arguments.

Then:

```text
Hook B
```

receives those rewritten arguments.

Conceptually:

```text
Original args
     │
     ▼
  Hook A
     │
     ▼
Modified args
     │
     ▼
  Hook B
     │
     ▼
Further modified args
     │
     ▼
   Tool
```

This is why `run_pre()` threads the arguments through the registered hooks.

The hook system isn't simply a collection of notifications.

It is a **processing pipeline**.

* * *

# Post-hooks form a similar pipeline

The same idea applies to results.

```text
Tool result
    │
    ▼
Post-hook A
    │
    ▼
Modified result
    │
    ▼
Post-hook B
    │
    ▼
Final result
```

This opens the door to composing multiple behaviors.

For example:

```text
Tool
 ↓
timing
 ↓
metrics
 ↓
redaction
 ↓
model
```

Each hook has a focused responsibility.

* * *

# Permissions versus hooks

This distinction is important enough to make explicit.

## Permissions

Permissions answer:

> **Is the tool call allowed?**

They are the primary authorization boundary.

The v0.7 implementation deliberately runs permissions first.

## Pre-hooks

Pre-hooks answer:

> **What should happen before this allowed tool runs?**

They can:

*   observe
    
*   modify arguments
    
*   add custom blocking
    

## Post-hooks

Post-hooks answer:

> **What should happen after the tool runs?**

They can:

*   observe
    
*   collect metrics
    
*   modify results
    
*   redact output
    

So:

```text
Permission
    ↓
"Can this happen?"

Pre-hook
    ↓
"What should happen before it?"

Tool
    ↓
"Perform the capability"

Post-hook
    ↓
"What should happen after it?"
```

Keeping these responsibilities separate makes the architecture easier to reason about.

* * *

# The complete v0.7 execution pipeline

We now have:

```text
                         ┌─────────────┐
                         │     LLM     │
                         └──────┬──────┘
                                │
                           tool request
                                │
                                ▼
                     ┌────────────────────┐
                     │ PermissionChecker  │
                     └─────────┬──────────┘
                               │
                         permission OK
                               │
                               ▼
                     ┌────────────────────┐
                     │     Pre-hooks      │
                     │                    │
                     │ log / rewrite /    │
                     │ block / validate   │
                     └─────────┬──────────┘
                               │
                               ▼
                     ┌────────────────────┐
                     │    Tool executes   │
                     └─────────┬──────────┘
                               │
                               ▼
                     ┌────────────────────┐
                     │    Post-hooks     │
                     │                    │
                     │ metrics / redact / │
                     │ transform / log    │
                     └─────────┬──────────┘
                               │
                               ▼
                         Tool result
                               │
                               ▼
                              LLM
```

This is starting to look like an actual agent runtime.

* * *

# Why hooks are better than modifying the agent loop

Without hooks, adding a feature like timing might require:

```python
start = time.perf_counter()

result = TOOLS[tool_name](**args)

duration = time.perf_counter() - start
```

Then redaction might add:

```python
result = redact(result)
```

Then metrics:

```python
counter.increment(...)
```

Then custom policy:

```python
if ...:
    ...
```

Then tracing:

```python
...
```

Eventually the core tool loop becomes a large collection of unrelated concerns.

Hooks allow the loop to remain conceptually simple. After permission approval, it must still honor the pre-hook's decision before executing the tool:

```python
allowed, reason, args = hooks.run_pre(...)
if allowed:
    result = execute_tool(...)
    result = hooks.run_post(...)
```

The complexity moves into independently testable components.

That is a much healthier architecture.

* * *
# Hooks are an extension point

This is perhaps the most important architectural lesson from v0.7.

The hook manager creates an **extension point**.

Today we have:

```text
TimingLogger
Counter
BlockTool
Redaction
```

Tomorrow we could add:

```text
OpenTelemetry tracing
audit logging
cost tracking
token accounting
policy enforcement
rate limiting
input validation
output validation
PII filtering
secret detection
tool retry
result caching
```

without changing every tool.

That is the power of an extension point.

* * *

# A subtle security lesson: permissions still come first

It might be tempting to think:

> "Now that we have hooks, hooks can replace permissions."

They shouldn't.

The intended pipeline is:

```text
permission check
       ↓
pre-hooks
       ↓
tool
       ↓
post-hooks
```

Permissions are the hard authorization gate.

Hooks are customizable behavior layered on top.

That distinction matters because a pre-hook should not be able to turn a permission denial into an approval.

The v0.7 lesson explicitly preserves this ordering.

* * *

# Testing the hook system

The repository includes dedicated tests for the hook behavior.

The tests cover:

*   pre-hook blocking
    
*   allowing unrelated tools
    
*   argument rewriting
    
*   hook ordering
    
*   tool usage counting
    
*   result redaction
    
*   leaving clean results untouched
    

That is useful because hook systems can become difficult to reason about once multiple callbacks interact.

Testing the manager independently keeps the behavior explicit.

For example, the argument-rewrite test verifies that:

```text
/etc/hosts
```

becomes:

```text
etc/hosts
```

before continuing.

The redaction test verifies that the sensitive portion of an API-key-like value does not remain in the returned result.

These are small tests, but they define the contract of the hook system.

* * *

# A useful mental model: agent middleware

At this point, I find it useful to think about the harness as having middleware.

A request enters:

```text
LLM tool request
```

Then it passes through layers:

```text
                 Tool Request
                      │
                      ▼
             ┌─────────────────┐
             │   Permissions   │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │    Pre-hooks    │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │      Tool       │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │   Post-hooks   │
             └────────┬────────┘
                      │
                      ▼
                 Observation
```

This is very similar to middleware pipelines found in conventional distributed systems.

The difference is that the thing being mediated is an **LLM-generated action**.

* * *

# Why this matters for production AI agents

A production agent cannot just be:

```text
LLM + tools
```

It needs operational controls around those tools.

For example:

```text
authorization
observability
auditing
redaction
policy
rate limits
cost controls
```

Lifecycle hooks provide a natural mechanism for many of these concerns.

This is particularly important because AI agents are dynamic.

The exact sequence of tool calls is not necessarily known in advance.

A user may ask one question, and the agent might execute ten different tools.

Therefore, cross-cutting controls need to work consistently regardless of which tools the model chooses.

Hooks provide that consistency.

* * *

# What I learned from v0.7

The biggest lesson from this version is:

> **Don't put cross-cutting behavior inside every tool. Put it around the tool execution boundary.**

Permissions gave us a centralized authorization layer.

Hooks now give us a centralized extension layer.

The architecture is becoming:

```text
LLM
 ↓
Permission
 ↓
Hooks
 ↓
Tools
 ↓
Hooks
 ↓
LLM
```

That is much more flexible than putting everything into individual tool implementations.

* * *

# The agent harness is starting to look like a runtime

When this project started, the agent was almost just:

```text
LLM → function → result
```

Now we have:

```text
                     Agent Runtime
                          │
          ┌───────────────┼────────────────┐
          │               │                │
     LLM Provider     Permissions       Hooks
          │               │                │
          └───────────────┼────────────────┘
                          │
                         Tools
                          │
              ┌───────────┼───────────┐
              │           │           │
           Filesystem    Shell      Code
```

That is the direction I wanted from this project.

Instead of starting with a large agent framework and accepting its abstractions, I am adding one primitive at a time and seeing why it is needed.

* * *

# What comes next?

We now have tools, providers, permissions, and lifecycle hooks.

But there is still a major limitation.

The agent's knowledge largely exists inside the current conversation.

If I stop the process and start it again, the agent does not automatically know what happened previously.

That leads to the next major question:

> **How should an AI agent remember information across tasks and sessions?**

That brings us to the next capability in the series: **memory**.

The interesting part is that memory isn't simply "save the chat history."

We need to think about:

*   what is worth remembering
    
*   where memory should live
    
*   how memory is retrieved
    
*   when memory should be written
    
*   how stale memory is handled
    
*   how memory affects the agent's context
    

And that will take us from a tool-using agent toward a more persistent agent architecture.

* * *

# The series so far

This is **Part 7** of my *Agents Zero to Hero* series, where I am building an AI coding-agent harness from first principles, one Git tag at a time.

1.  **v0.1 — Tool Calling** Build the basic LLM → tool → observation loop.
    
2.  **v0.2 — Filesystem Tools** Give the agent the ability to explore and modify a workspace.
    
3.  **v0.3 — Shell Execution** Give the agent controlled command execution.
    
4.  **v0.4 — Code Editing and Search** Give the agent better primitives for navigating and modifying source code.
    
5.  **v0.5 — Multiple LLM Providers** Separate the agent harness from the underlying model provider.
    
6.  **v0.6 — Permissions** Control which model-requested actions are allowed.
    
7.  **v0.7 — Lifecycle Hooks** Add reusable behavior around tool execution without modifying the tools.
    

The repository contains each checkpoint as a Git tag so that the architecture can be studied incrementally.

The goal is not to build the largest AI agent framework.

The goal is to understand **what an agent harness actually needs and why each abstraction exists.**

* * *

# Key takeaway

An AI agent needs more than tools.

It also needs a way to control and observe those tools.

A useful execution pipeline is:

```text
LLM
 ↓
Permission check
 ↓
Pre-hook
 ↓
Tool
 ↓
Post-hook
 ↓
Observation
 ↓
LLM
```

Permissions answer:

> **Is this action allowed?**

Hooks answer:

> **What should happen around this action?**

That separation gives the agent harness a clean extension point for logging, metrics, policy enforcement, argument rewriting, and secret redaction.

And most importantly, we can add those capabilities **without turning every tool or the core agent loop into a giant piece of infrastructure code.**

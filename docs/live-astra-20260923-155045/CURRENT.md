# Agents Zero to Hero #12: Building AI Subagents with Context Isolation

## Agents Zero to Hero #12: Building AI Subagents with Context Isolation

So far, my AI coding agent has been doing everything itself.

It can:

*   use tools
    
*   modify files
    
*   execute commands
    
*   remember information
    
*   compact long conversations
    
*   load skills on demand
    
*   connect to external MCP tools
    

But there is a scaling problem.

As a task gets larger, the agent's context starts accumulating everything:

```text
original task
    ↓
planning
    ↓
file exploration
    ↓
tool calls
    ↓
tool results
    ↓
research
    ↓
more tool calls
    ↓
more results
```

Eventually, the agent has to carry the details of every subtask in one conversation.

Context compaction from `v0.9` helps, but it doesn't solve the fundamental problem.

Sometimes the better solution is:

> **Don't put every subtask into the same context. Delegate it.**

In `v0.12-subagents`, I added a `spawn_subagent` tool.

The main agent can now delegate a self-contained task to a fresh child agent:

```text
Parent Agent
     │
     │ spawn_subagent("do X")
     ▼
Child Agent
     │
     │ fresh context
     │ same tools
     │ same policy
     ▼
   result
     │
     ▼
Parent Agent
```

The child does the messy work.

The parent receives only the result.

This is the beginning of a **multi-agent or agent-swarm architecture**.

* * *

# What is an AI subagent?

An AI subagent is another agent instance that is created by a parent agent to perform a specific task.

The important word is **specific**.

A parent shouldn't delegate:

```text
"Do everything."
```

It should delegate something like:

```text
"Inspect the authentication module and identify the files that need changes."
```

or:

```text
"Run the tests and summarize the failures."
```

or:

```text
"Refactor this module and report what you changed."
```

The child gets its own reasoning loop:

```text
receive task
    ↓
inspect context
    ↓
use tools
    ↓
solve subtask
    ↓
finish
    ↓
return result
```

The parent continues its own loop using the child's answer.

* * *

# Why do AI agents need subagents?

Consider a large task:

```text
"Add authentication to this application."
```

A single agent might need to:

```text
1. Explore repository
2. Understand current authentication
3. Inspect database models
4. Inspect API routes
5. Design changes
6. Modify implementation
7. Add tests
8. Run tests
9. Debug failures
10. Update documentation
```

All of that information accumulates in one context.

Instead, the parent can delegate:

```text
Parent
 ├── investigate authentication architecture
 ├── inspect database models
 ├── implement API changes
 └── run tests
```

Each child can focus on one responsibility.

The parent then receives concise results.

* * *

# The key idea: context isolation

This is the most important concept in `v0.12`.

A subagent does **not** inherit the parent's conversation history.

Instead:

```text
Parent context
────────────────────────────
system
original task
planning
tool call
tool result
tool call
tool result
...
```

The child starts with:

```text
Child context
────────────────────────────
system
subtask
```

That means the child doesn't automatically see every intermediate thought and tool result from the parent.

The parent sees:

```text
{
    "subagent_result": "..."
}
```

rather than the child's entire history.

So delegation becomes a form of **context management**.

* * *

# How does `spawn_subagent()` work?

The implementation is intentionally simple.

There isn't a separate `Subagent` class.

There isn't another agent framework.

The implementation uses the existing:

```python
run_agent()
```

function.

The idea is:

```text
spawn_subagent(task)
        ↓
run_agent(task)
        ↓
child agent
```

In other words:

> **A subagent is another invocation of the same agent loop.**

This is a powerful simplification.

There is only one core agent implementation.

* * *

# The parent-child relationship

The architecture looks like this:

```text
                 run_agent()
                     │
                 depth = 0
                     │
                     ▼
              ┌─────────────┐
              │    Parent   │
              │    Agent    │
              └──────┬──────┘
                     │
              spawn_subagent()
                     │
                     ▼
              ┌─────────────┐
              │    Child    │
              │    Agent    │
              └─────────────┘
                  depth = 1
```

The child itself calls:

```python
run_agent()
```

with:

```text
depth + 1
```

This gives us a natural way to control recursion.

* * *

# Why does the child need a fresh context?

Imagine the parent has already accumulated:

```text
20 tool calls
10 file contents
5 test outputs
3 previous plans
2 compaction summaries
```

Now it needs to investigate one small question.

If that entire history is passed to the child, we've gained very little.

The child should instead receive:

```text
"Inspect the database models and tell me how users are represented."
```

Its context becomes focused on exactly that task.

The child might perform:

```text
list_files
read_file
code_search
read_file
finish
```

The parent receives:

```text
"Users are represented by UserModel in models/user.py.
The API currently uses JWT authentication..."
```

The implementation details stay in the child's context.

* * *

# Subagents and context compaction solve different problems

This is an important distinction.

`v0.9` introduced **compaction**.

Compaction asks:

> How can I keep this conversation within a context budget?

Subagents ask:

> Should this work happen in this conversation at all?

Consider:

```text
Parent task
    │
    ├── Task A
    ├── Task B
    ├── Task C
    └── Task D
```

Without delegation:

```text
One huge context
──────────────────────────────
A + B + C + D
```

With delegation:

```text
Parent context
────────────────
high-level task
A result
B result
C result
D result

Child A context
────────────────
Task A details

Child B context
────────────────
Task B details

Child C context
────────────────
Task C details

Child D context
────────────────
Task D details
```

Compaction reduces the size of a context.

Delegation prevents unrelated detail from entering the context in the first place.

* * *

# How is `spawn_subagent` exposed to the model?

The new tool has a schema:

```python
SPAWN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "spawn_subagent",
        ...
    }
}
```

Its important parameter is:

```text
task
```

The task is described as:

> A complete, standalone instruction for the subagent.

That's deliberate.

A child should not need to guess what the parent meant.

Good delegation requires a well-scoped instruction.

For example:

```text
Inspect the Python files under the authentication module.
Identify how authentication currently works and list the files
that would need changes to support OAuth. Do not modify files.
Return a concise summary.
```

is much better than:

```text
Look at auth.
```

* * *

# How does the parent receive the result?

The child eventually calls:

```text
finish(answer)
```

The child's `run_agent()` returns that answer.

The parent-side wrapper converts it into:

```python
{
    "subagent_result": answer
}
```

So the parent's context gets a normal tool result:

```text
spawn_subagent(...)
        ↓
{
    "subagent_result": "..."
}
```

The parent can then continue reasoning.

This is another nice property of the implementation:

> **Delegation looks like an ordinary tool call to the parent.**

* * *

# Why not expose the entire child conversation?

Because that would defeat the purpose.

Suppose the child performs:

```text
list_files
read_file
read_file
code_search
read_file
bash
read_file
edit_file
bash
...
```

The parent doesn't necessarily need all of that.

It usually needs:

```text
what was discovered
what changed
what failed
what remains
```

So the interface is:

```text
Parent
  │
  │ task
  ▼
Child
  │
  │ detailed internal context
  │
  ▼
summary/result
  │
  ▼
Parent
```

This is essentially **information compression at an agent boundary**.

* * *

# The child still has the same tools

The child isn't a weaker version of the parent.

It gets the same core agent infrastructure.

The implementation passes the same:

```text
permissions
hooks
memory
workspace
model
```

to the child.

Conceptually:

```python
run_agent(
    task,
    permissions=permissions,
    hooks=hooks,
    memory=memory,
    ...
)
```

So the child can still use:

```text
list_files
read_file
write_file
bash
edit_file
code_search
remember
skills
MCP tools
```

depending on what is available.

The difference is the **context**, not the fundamental capabilities.

* * *

# What does "shared workspace" mean?

The parent and child operate on the same workspace.

For example:

```text
agent_workspace/
    app.py
    tests/
    config.py
```

If the child creates:

```text
greet.txt
```

the parent can see it.

The filesystem is therefore shared:

```text
             Parent
                │
                │
                ▼
       ┌─────────────────┐
       │ Shared workspace│
       └─────────────────┘
                ▲
                │
                │
              Child
```

This is useful for implementation tasks.

For example:

```text
Parent:
"Implement feature X."

Child:
"Create the initial implementation."

Parent:
"Now review what the child changed and run tests."
```

Both agents see the same files.

* * *

# Shared workspace, isolated context

This distinction is central.

The child shares:

```text
workspace
permissions
hooks
memory
```

but does **not** share:

```text
conversation history
```

So:

```text
                Parent
                   │
       ┌───────────┼───────────┐
       │           │           │
       ▼           ▼           ▼
   Workspace   Permissions   Hooks
       ▲           ▲           ▲
       │           │           │
       └───────────┼───────────┘
                   │
                 Child

          Context is separate
```

This is the design tradeoff.

* * *

# Why share permissions and hooks?

Because delegation shouldn't be a way to bypass governance.

Imagine the parent is running in:

```text
AGENT_PERMISSION_MODE=plan
```

The parent shouldn't be able to say:

```text
spawn a child
```

and suddenly get a child that can modify files freely.

The child therefore receives the same policy objects:

```text
permissions
hooks
```

The governance boundary follows the agent.

This gives us:

```text
Parent policy
      │
      ├─────────────► Parent
      │
      └─────────────► Child
```

rather than:

```text
Parent policy
      │
      ▼
Parent

Child
   └── unrestricted
```

* * *

# The biggest danger: recursive spawning

Once an agent can create another agent, the obvious question is:

> What's stopping the child from creating another child?

Without a limit:

```text
Agent
 └── Agent
      └── Agent
           └── Agent
                └── Agent
                     ...
```

This could continue indefinitely.

It can cause:

*   runaway API usage
    
*   runaway compute
    
*   excessive file modifications
    
*   uncontrolled recursion
    
*   difficult-to-debug behavior
    

So `v0.12` introduces an explicit depth limit.

* * *

# How does the depth guard work?

`run_agent()` now accepts:

```python
depth=0
max_depth=1
```

The parent starts at:

```text
depth = 0
```

If it creates a child:

```text
depth = 1
```

With the default:

```text
max_depth = 1
```

the child cannot create another subagent.

The tree therefore becomes:

```text
depth 0
   │
   ├── depth 1
   ├── depth 1
   └── depth 1
```

but not:

```text
depth 0
   │
   └── depth 1
          │
          └── depth 2   ← blocked
```

* * *

# Why is the tool only advertised at permitted depth?

The implementation doesn't just rely on the runtime check.

It only adds the `spawn_subagent` schema when:

```python
if depth < max_depth:
```

So the child doesn't normally see:

```text
spawn_subagent
```

in its tool list.

That's better than exposing a tool that will always fail.

The runtime still has a guard as a defense in depth.

* * *

# What happens if the model tries anyway?

There is another small but important change in `v0.12`.

The agent loop now handles an unknown tool gracefully.

Previously, trying to execute an unavailable tool could result in a lookup failure.

Now the harness can return:

```json
{
  "error": "unknown tool: spawn_subagent"
}
```

instead of crashing.

This is useful for the depth boundary:

```text
Child
  │
  │ attempts spawn_subagent
  ▼
Tool unavailable
  │
  ▼
error returned to model
  │
  ▼
model can continue
```

The agent isn't terminated just because it requested an unavailable capability.

* * *

# A concrete parent-child example

Suppose the parent receives:

```text
Create greet.txt containing "hi from the subagent".
```

The parent decides to delegate:

```text
spawn_subagent(
    task="Create greet.txt containing 'hi from the subagent'."
)
```

The child starts with a fresh context.

It might do:

```text
list_files
    ↓
write_file("greet.txt", ...)
    ↓
finish("Created greet.txt")
```

The child returns:

```json
{
  "subagent_result": "Created greet.txt"
}
```

The parent receives that result and can finish:

```text
"The subagent created greet.txt successfully."
```

The child's intermediate tool traffic never becomes part of the parent's conversation.

* * *

# What does the actual demo do?

The `v0.12` demo can be enabled with:

```bash
AGENT_SUBAGENT=1 python coding_agent.py
```

The task is effectively:

```text
Delegate to a subagent the task of creating greet.txt
containing "hi from the subagent".
When it reports done, finish with its result.
```

The expected execution is:

```text
Parent
  │
  ├── spawn_subagent(...)
  │
  │      Child
  │        │
  │        ├── list_files
  │        ├── write_file
  │        └── finish(...)
  │
  └── finish(...)
```

This is intentionally small.

The goal is to demonstrate the delegation mechanism, not build a sophisticated swarm scheduler yet.

* * *

# How are subagents different from parallel tool calls?

This is an important distinction.

A model might already request multiple tools:

```text
read_file(A)
read_file(B)
read_file(C)
```

Those are still tool calls within the same agent context.

A subagent is different:

```text
parent context
      │
      └── child context
```

The child gets its own:

```text
message history
reasoning loop
iteration budget
tool interactions
```

So delegation changes the **context boundary**, not just the number of operations.

* * *

# Subagents are a form of context architecture

This connects directly to the previous versions.

We started with:

### v0.8 — Memory

```text
What should survive between runs?
```

### v0.9 — Compaction

```text
How do we keep one long conversation within a context budget?
```

### v0.10 — Skills

```text
What reusable knowledge should we load only when needed?
```

### v0.12 — Subagents

```text
Which work should happen in a separate context altogether?
```

So the project is gradually building a broader context-management strategy:

```text
                 Context management
                        │
        ┌───────────────┼────────────────┐
        │               │                │
        ▼               ▼                ▼
     Memory        Compaction        Delegation
        │               │                │
   across runs     within run       across agents
```

This is one of the deeper lessons of the project.

* * *

# Subagents versus skills

The two can also work together.

A child might receive a task requiring Python conventions.

It can use:

```text
load_skill("python-style")
```

So:

```text
Parent
  │
  └── spawn_subagent
          │
          ▼
       Child
          │
          └── load_skill("python-style")
```

This gives the child:

```text
isolated task context
+
reusable domain knowledge
```

The architecture is becoming composable.

* * *

# Subagents versus MCP

The same is true for MCP.

A child can potentially use an MCP tool available to the harness:

```text
Parent
  │
  └── Child
       │
       └── mcp__some_tool
```

This creates a useful separation:

```text
Subagents
    → who performs the work

Skills
    → what knowledge they can load

MCP
    → what external capabilities they can access

Tools
    → what actions they can perform
```

Those are different dimensions of an agent system.

* * *

# A useful mental model: delegation as a context firewall

I think the simplest mental model for this version is:

> **A subagent is a context firewall.**

The parent sends in:

```text
task
```

The child performs:

```text
many intermediate steps
```

The parent receives:

```text
result
```

So:

```text
                 Context Firewall

Parent context
────────────────────────────────
Task
Plan
Previous work
Tool history
...
       │
       │ scoped task
       ▼
┌───────────────────────────────┐
│          Child context        │
│                               │
│ exploration                   │
│ files                         │
│ commands                      │
│ reasoning                     │
│ tool results                  │
│ implementation                │
└───────────────────────────────┘
       │
       │ result
       ▼
Parent context
────────────────────────────────
Task
Child result
...
```

The firewall prevents all of that intermediate detail from flooding the parent.

* * *

# Why the child should receive a scoped task

Delegation only works well if the task boundary is clear.

Bad:

```text
"Investigate the project."
```

Better:

```text
"Inspect the authentication module and identify how
user sessions are currently persisted. Return the relevant
files and a concise explanation. Do not modify anything."
```

The second task has:

*   clear scope
    
*   clear output
    
*   clear side-effect boundary
    

This matters because the parent is effectively creating a new autonomous process.

* * *

# The parent remains the orchestrator

The child isn't necessarily responsible for the overall objective.

The parent owns the larger plan.

For example:

```text
Parent:
"Implement feature X."

        │
        ├── Child A: understand existing implementation
        │
        ├── Child B: inspect test coverage
        │
        └── Child C: investigate dependency options

        ↓

Parent synthesizes results
        ↓
Implementation
        ↓
Verification
```

This is the beginning of an orchestrator/worker architecture.

* * *

# Testing subagent delegation

The repository includes:

```text
tests/test_subagents.py
```

The tests use a fake model, so they don't require an API key.

The first test scripts:

```text
parent → spawn_subagent
child  → finish("CHILD_OK")
parent → finish("DONE")
```

Then it verifies:

```python
self.assertEqual(result, "DONE")
```

and:

```python
self.assertEqual(fake.completions.i, 3)
```

Three model calls prove that the child actually ran:

```text
1. parent model call
2. child model call
3. parent model call
```

That's a nice test because it verifies actual delegation rather than simply testing the wrapper function.

* * *

# Testing the depth guard

The second test uses:

```text
max_depth=0
```

The model still attempts:

```text
spawn_subagent
```

but no child is created.

The test confirms that only the parent's calls happen.

This establishes an important invariant:

> **The number of agent generations is bounded by** `max_depth`**.**

For the default:

```text
max_depth = 1
```

the hierarchy cannot continue beyond one child generation.

* * *

# The architecture after v0.12

The agent now looks roughly like:

```text
                         Parent Agent
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
          Tools            Skills            MCP
             │                │                │
             └────────────────┼────────────────┘
                              │
                        spawn_subagent
                              │
                              ▼
                         Child Agent
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
           Tools           Skills            MCP
                              │
                              ▼
                         shared workspace
```

Both agents still have the same underlying infrastructure:

```text
permissions
hooks
memory
compaction
skills
MCP
tools
```

But each agent gets its own message history.

* * *

# What is shared and what is isolated?

This is worth summarizing explicitly.

| Component | Parent / Child |
| --- | --- |
| Message history | **Isolated** |
| Agent reasoning loop | Separate |
| Task | Different |
| Workspace | **Shared** |
| Permissions | **Shared** |
| Hooks | **Shared** |
| Memory object | **Shared** |
| Tools | Same tool set |
| MCP connections | Available through inherited tool configuration |
| Depth | Incremented |
| Result | Child returns to parent |

The most important boundary is:

```text
conversation = isolated
workspace = shared
policy = shared
```

* * *

# Why not isolate the workspace too?

That would be a different architecture.

If every subagent had a separate filesystem, collaboration would require an explicit mechanism for transferring artifacts:

```text
Child workspace
      ↓
export artifact
      ↓
Parent workspace
```

The current implementation intentionally avoids that complexity.

Sharing the workspace makes delegation immediately useful for coding tasks.

For example:

```text
Child:
modify module.py

Parent:
inspect module.py
run tests
```

The result is already visible.

* * *

# But shared workspace creates coordination challenges

This is where the next level of multi-agent engineering begins.

If two children both modify:

```text
app.py
```

we can get conflicts.

For example:

```text
Parent
 ├── Child A → edit app.py
 └── Child B → edit app.py
```

Now we need coordination.

Potential future mechanisms include:

```text
file locks
worktrees
patches
branches
ownership
task queues
conflict detection
```

The current version intentionally doesn't solve these problems yet.

It establishes the basic delegation primitive first.

* * *

# Why depth is not the same as concurrency

`max_depth` controls:

```text
how far delegation can recursively continue
```

It does not control:

```text
how many children can exist
```

With:

```text
max_depth = 1
```

the parent could theoretically create:

```text
Parent
 ├── Child A
 ├── Child B
 ├── Child C
 └── Child D
```

Each child is depth 1.

The next evolution of the architecture will likely need more explicit orchestration controls:

```text
max_children
concurrency limit
budget
timeout
```

Those are separate concerns.

* * *

# Cost is another important boundary

Every subagent is another LLM execution.

So delegation can improve context management while increasing:

```text
model calls
latency
token usage
cost
```

That means:

> **A subagent should be created because the isolation is valuable, not simply because another model call is available.**

For a trivial task:

```text
"Rename variable x to y."
```

creating a child is probably unnecessary.

For a complex independent task:

```text
"Analyze the entire authentication subsystem and report the architecture."
```

a separate context can make much more sense.

* * *

# Subagents are not automatically better

This is an important engineering tradeoff.

Single agent:

```text
simple
cheap
low coordination overhead
one context
```

Subagents:

```text
better isolation
parallelization potential
specialized tasks
more orchestration complexity
more model calls
```

The right architecture depends on the task.

The point of `v0.12` isn't to say:

> “Always use subagents.”

It is to add **delegation as another primitive**.

* * *

# The journey so far

At `v0.12`, the project now has:

| Version | Capability | Main idea |
| --- | --- | --- |
| `v0.1` | Tool calling | LLM can act |
| `v0.2` | File tools | LLM can inspect files |
| `v0.3` | Bash | LLM gets a guarded shell |
| `v0.4` | Edit/search | Precise code manipulation |
| `v0.5` | Multi-provider | Provider abstraction |
| `v0.6` | Permissions | Governance |
| `v0.7` | Hooks | Middleware |
| `v0.8` | Memory | Persistent context |
| `v0.9` | Compaction | Bounded context |
| `v0.10` | Skills | On-demand knowledge |
| `v0.11` | MCP | External capabilities |
| `v0.12` | Subagents | Delegated, isolated work |

There is now a fairly complete set of primitives around a single agent.

And the architecture is starting to shift from:

```text
single agent
```

toward:

```text
agent system
```

* * *

# What's next?

There is one major capability left in this 13-step curriculum:

```text
v0.13-verify-loop
```

So far, the agent can modify code.

But an important question remains:

> **How does the agent know that its changes actually work?**

A coding agent shouldn't stop merely because it successfully called `write_file()`.

The stronger loop is:

```text
implement
   ↓
run tests
   ↓
observe failure
   ↓
understand failure
   ↓
modify code
   ↓
run tests again
   ↓
repeat
   ↓
verified result
```

That turns the agent loop from:

```text
reason → act → finish
```

into:

```text
reason → act → verify → repair → verify → finish
```

That will be the focus of `v0.13`.

* * *

# Final takeaway

The important idea in `v0.12` is not simply that an agent can create another agent.

It is that **delegation creates a new context boundary**.

The parent says:

```text
"Handle this scoped task."
```

The child gets:

```text
fresh context
same tools
same policy
shared workspace
```

The child does its work.

The parent receives:

```text
the result
```

rather than the entire execution history.

So the architecture becomes:

```text
                    Parent Agent
                         │
                 scoped delegation
                         │
                         ▼
                   Child Agent
                         │
                isolated context
                         │
                         ▼
                      result
                         │
                         ▼
                    Parent Agent
```

And the safety rule is simple:

```text
Never let delegation become unbounded recursion.
```

That is why `depth` and `max_depth` are not just implementation details—they are part of the architecture.

With `v0.12`, the agent has learned something new:

**When a problem becomes too large for one context, it can create a smaller context and hand the problem to another agent.**

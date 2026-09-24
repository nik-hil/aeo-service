# Agents Zero to Hero #8: Teaching an AI Agent to Remember

## Agents Zero to Hero #8: Teaching an AI Agent to Remember

**Building persistent memory, project context, and session resume into a coding agent from scratch.**

So far, our coding agent has become increasingly capable.

It can execute code.

It can read and write files.

It can run a guarded shell.

It can search and edit code.

It can work with multiple LLM providers.

It has permissions.

It has lifecycle hooks for logging, metrics, redaction, and policy enforcement.

But there is still one major problem.

Every time we start the agent, it wakes up with **amnesia**.

It doesn't know what happened in the previous run.

It doesn't remember important facts.

It doesn't automatically know the project's instructions.

And if we stop halfway through a task, the next invocation starts from scratch.

That's what `v0.8-memory` fixes.

The goal of this lesson is not to build a complicated vector database or a sophisticated retrieval system.

Instead, we're going to answer a much simpler question:

> **What is the minimum architecture required to give an AI agent persistent memory?**

The answer is surprisingly simple:

**Files + a tool to write them + injecting those files back into the prompt.**

* * *

## What does memory mean for an AI agent?

Before writing code, we need to distinguish three different kinds of information.

An agent doesn't necessarily need one giant "memory" system.

There are at least three useful categories:

| Type | File | Writer | Lifetime |
| --- | --- | --- | --- |
| Project context | `AGENTS.md` / `CLAUDE.md` | Human | Project lifetime |
| Persistent memory | `MEMORY.md` | Agent | Across runs |
| Session history | `.agent_sessions/<name>.json` | Harness | Resume a session |

These solve different problems.

### 1\. Project context

This is information that the human deliberately provides to the agent.

For example:

```text
Always add type hints to new Python functions.

Run unit tests before considering a task complete.

Do not modify files outside the repository.
```

This belongs in something like:

```text
AGENTS.md
```

or:

```text
CLAUDE.md
```

The important distinction is that **the human owns this information**.

* * *

### 2\. Persistent memory

Sometimes the agent discovers something during a task that should survive the current run.

For example:

```text
The project uses Python 3.12.

The deployment happens every Friday.

The authentication service is located in services/auth/.
```

These facts can be stored in:

```text
MEMORY.md
```

The agent can add a note through the new `remember` tool.

* * *

### 3\. Session history

Memory isn't the same thing as conversation history.

Suppose the agent was halfway through a task:

```text
User: Fix the authentication bug.

Agent: I found the problem in auth.py.

Agent: I'm going to modify the token validation logic...
```

The process stops.

When we start again, we may want to resume that conversation.

That's what:

```text
.agent_sessions/demo.json
```

is for.

The harness stores a transcript and can replay it into the next run.

* * *

# The key insight: memory is prompt context

The most important idea in this lesson is that an LLM doesn't inherently "remember" files.

The model only knows what we provide in its context.

So if we want the agent to remember something, the harness needs to:

1.  Persist the information.
    
2.  Load it later.
    
3.  Put it into the model's prompt.
    

Conceptually:

```text
             Persistent storage
                    │
          ┌─────────┼─────────┐
          │         │         │
       AGENTS.md MEMORY.md Session
          │         │         │
          └─────────┼─────────┘
                    │
                    ▼
             System prompt
                    │
                    ▼
                   LLM
```

There is no magic involved.

The memory exists because the harness puts the information back into the model's context.

* * *

# Introducing `memory.py`

The new component is deliberately small.

```python
@dataclass
class Memory:
    base_dir: Path
    memory_file: str = "MEMORY.md"
```

The `Memory` class has four important responsibilities:

```text
load_context()
load_memory()
remember()
system_addendum()
```

Let's look at each one.

* * *

# How does an AI agent load project context?

The first method is:

```python
def load_context(self) -> str:
```

It looks for:

```text
AGENTS.md
CLAUDE.md
```

and loads whichever files exist.

The implementation keeps the context explicit:

```python
CONTEXT_FILENAMES = ["AGENTS.md", "CLAUDE.md"]
```

Then:

```python
for name in CONTEXT_FILENAMES:
    p = self.base_dir / name

    if p.is_file():
        parts.append(
            f"### {name}\n"
            f"{p.read_text(encoding='utf-8').strip()}"
        )
```

The result becomes text that can be injected into the system prompt.

This is useful because project instructions remain:

*   human-readable
    
*   version-controllable
    
*   easy to edit
    
*   independent of the agent implementation
    

For example:

```markdown
# AGENTS.md

- Use Python 3.12.
- Add tests for new functionality.
- Do not modify generated files.
- Keep functions small and typed.
```

The agent doesn't need a special database query to retrieve this.

The harness simply reads the file.

* * *

# How does an AI agent remember something?

The second piece is persistent memory.

The agent gets a new tool:

```python
remember(note: str)
```

Internally it calls:

```python
MEMORY.remember(note)
```

Whitespace-only notes are rejected with an error rather than written. For a non-empty note, the implementation appends a timestamped entry:

```python
stamp = time.strftime("%Y-%m-%d %H:%M")

with open(p, "a", encoding="utf-8") as f:
    f.write(f"- ({stamp}) {note}\n")
```

So if the agent says:

```text
Remember that this project is the agents-zero-2-hero tutorial harness.
```

the resulting file can contain something like:

```markdown
- (2026-09-16 14:30) This project is the agents-zero-2-hero tutorial harness.
```

On the next run, that file is loaded again.

This gives us persistent memory with almost no infrastructure.

* * *
# Why append instead of overwrite?

The implementation intentionally appends notes:

```python
with open(p, "a", encoding="utf-8") as f:
```

rather than replacing the entire file.

That means multiple memory entries can accumulate:

```markdown
- (2026-09-16 14:30) Project uses Python 3.12.
- (2026-09-16 14:31) Deployment runs through Docker.
- (2026-09-16 14:32) Authentication code lives in services/auth/.
```

This is a very simple memory model.

It also exposes an important limitation.

**Persistent storage is not the same thing as intelligent memory management.**

If we allow unlimited notes, `MEMORY.md` can eventually become huge.

That becomes important when we reach context compaction in `v0.9`.

* * *

# What happens when memory is empty?

The implementation also handles the first run cleanly.

```python
def load_memory(self) -> str:
    p = self.base_dir / self.memory_file

    return (
        p.read_text(encoding="utf-8").strip()
        if p.is_file()
        else ""
    )
```

If `MEMORY.md` doesn't exist:

```text
""
```

is returned.

No database initialization.

No migration.

No schema.

No special bootstrap process.

The first call to `remember()` creates the file.

* * *

# Combining context and memory

Now we need to turn all this information into something the LLM can actually see.

That's the job of:

```python
system_addendum()
```

It builds two sections:

```text
## Project context

...

## Remembered notes (persistent memory)

...
```

Conceptually:

```python
blocks = []

ctx = self.load_context()

if ctx:
    blocks.append("## Project context\n" + ctx)

mem = self.load_memory()

if mem:
    blocks.append(
        "## Remembered notes (persistent memory)\n" + mem
    )

return "\n\n".join(blocks).strip()
```

This is the bridge between **persistent storage** and **LLM context**.

* * *

# How does the harness inject memory into the LLM?

The `coding_agent.py` file creates the memory system at the repository root:

```python
PROJECT_ROOT = WORKSPACE.parent

MEMORY = Memory(PROJECT_ROOT)
SESSIONS = SessionStore(PROJECT_ROOT)
```

This is an important design choice.

The agent's scratch workspace is:

```text
agent_workspace/
```

But persistent memory lives outside it:

```text
MEMORY.md
AGENTS.md
.agent_sessions/
```

Conceptually:

```text
repository/
│
├── AGENTS.md
├── MEMORY.md
├── .agent_sessions/
│
├── coding_agent.py
├── memory.py
│
└── agent_workspace/
      ├── notes.txt
      └── other agent files
```

Why separate them?

Because the agent's workspace is disposable.

Memory should not disappear simply because the workspace is reset.

* * *

# Human context and agent memory are different

This distinction is subtle but important.

Consider:

```text
AGENTS.md
```

versus:

```text
MEMORY.md
```

`AGENTS.md` is **human-authored project context**.

`MEMORY.md` is **agent-authored persistent memory**.

That gives us a useful separation of responsibility:

```text
Human
  │
  ▼
AGENTS.md
  │
  │
Agent
  │
  ▼
MEMORY.md
```

The human controls the project's rules.

The agent can record useful facts it discovers.

Both eventually become context for the model.

* * *

# What is session memory?

Persistent memory and session history solve different problems.

The new:

```python
SessionStore
```

handles session transcripts.

Its storage format is intentionally simple:

```text
.agent_sessions/
    demo.json
    debugging.json
    refactor.json
```

Each file contains a list of messages.

For example:

```json
[
  {
    "role": "user",
    "content": "Fix the authentication bug"
  },
  {
    "role": "assistant",
    "content": "I found the issue in auth.py"
  }
]
```

* * *

# Saving a session

The implementation creates the session directory if required:

```python
self.dir.mkdir(parents=True, exist_ok=True)
```

and then writes JSON:

```python
p.write_text(
    json.dumps(transcript, indent=2),
    encoding="utf-8"
)
```

The result is deliberately boring.

That's a good thing for a learning project.

A session is just a transcript.

* * *

# Loading a session

The corresponding operation is:

```python
def load(self, name: str) -> list[dict] | None:
```

If the session exists:

```python
return json.loads(
    p.read_text(encoding="utf-8")
)
```

Otherwise:

```python
return None
```

Again, no database is required.

* * *

# Rendering a session for the prompt

The session transcript eventually needs to become context for the model.

The implementation does this with:

```python
def as_text(self, transcript):
    return "\n".join(
        f"{m['role']}: {m['content']}"
        for m in transcript
    )
```

For example:

```text
user: Fix the authentication bug
assistant: I found the issue in auth.py
tool: {"filepath": "auth.py"}
```

That text can then be injected into the prompt when resuming.

* * *

# The new agent lifecycle

We now have a much richer agent lifecycle.

Before v0.8:

```text
Start
  ↓
Create system prompt
  ↓
LLM
  ↓
Tools
  ↓
Finish
  ↓
Exit
```

After v0.8:

```text
Start
  │
  ├── Load AGENTS.md / CLAUDE.md
  │
  ├── Load MEMORY.md
  │
  ├── Load session transcript if resuming
  │
  ▼
Build system prompt
  │
  ▼
LLM
  │
  ├── permission check
  │
  ├── pre-hook
  │
  ├── tool execution
  │
  └── post-hook
  │
  ▼
LLM
  │
  ▼
remember(...)
  │
  ▼
MEMORY.md
```

Notice how the previous lessons continue to compose.

Memory doesn't replace permissions.

Memory doesn't replace hooks.

It becomes another layer around the agent loop.

* * *

# What does `remember` actually give the model?

Suppose the task says:

```text
Remember that this project is the agents-zero-2-hero tutorial harness.
```

The model calls:

```text
remember(
    "this project is the agents-zero-2-hero tutorial harness"
)
```

The harness writes:

```text
MEMORY.md
```

Now imagine we start the agent again.

The harness reads:

```text
MEMORY.md
```

and injects:

```text
## Remembered notes (persistent memory)

- (2026-09-16 14:30) This project is the agents-zero-2-hero tutorial harness.
```

The model now has that fact in its context.

That's persistent memory.

* * *

# Testing memory without an API key

One of the best parts of this lesson is that the memory subsystem is independently testable.

The repository adds:

```text
tests/test_memory.py
```

The tests use temporary directories.

That means they don't touch the real:

```text
MEMORY.md
.agent_sessions/
```

in the repository.

The tests cover several behaviors.

* * *

## Test 1: remember and load

The test creates a `Memory` instance and writes two notes:

```python
m.remember("favorite language is Python")
m.remember("deploys happen on Fridays")
```

Then it verifies both can be loaded.

This proves the persistence path works.

* * *

## Test 2: reject empty notes

The implementation rejects:

```python
m.remember("   ")
```

rather than creating meaningless entries.

The expected result contains:

```text
error
```

This is a small validation rule, but it keeps the memory file cleaner.

* * *

## Test 3: load project context

The test creates:

```text
AGENTS.md
```

inside a temporary directory.

Then:

```python
ctx = m.load_context()
```

must contain both:

```text
AGENTS.md
```

and its contents.

* * *

## Test 4: combine context and memory

This test is especially important.

It verifies that:

```text
Project context
```

and:

```text
Remembered notes
```

both appear in:

```python
system_addendum()
```

This validates the actual bridge into prompt context.

* * *

## Test 5: session round-trip

A transcript is saved:

```python
transcript = [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "done"},
]
```

Then loaded again.

The test expects:

```python
loaded == transcript
```

This proves session persistence.

* * *

# Running the new memory demo

The lesson provides a simple two-run experiment.

First run:

```bash
python coding_agent.py
```

The agent is instructed to remember a fact and create:

```text
notes.txt
```

You can inspect:

```bash
cat MEMORY.md
```

You should see the remembered note.

Now run again with session resume:

```bash
AGENT_SESSION=demo AGENT_RESUME=1 python coding_agent.py
```

The harness can now restore the previous transcript.

You can also modify:

```bash
AGENTS.md
```

and start the agent again.

The updated project context will be injected into the system prompt.

* * *

# Why memory lives outside the workspace

This is one of the architectural decisions worth paying attention to.

The code deliberately uses:

```python
PROJECT_ROOT = WORKSPACE.parent
```

and creates:

```python
MEMORY = Memory(PROJECT_ROOT)
SESSIONS = SessionStore(PROJECT_ROOT)
```

rather than storing memory under:

```text
agent_workspace/
```

Why?

Because the workspace represents the agent's working area.

Memory represents the harness's persistent state.

Keeping them separate gives us:

```text
Disposable agent state
        │
        ▼
agent_workspace/

Persistent harness state
        │
        ├── AGENTS.md
        ├── MEMORY.md
        └── .agent_sessions/
```

This is an important pattern for real agent systems.

* * *

# Memory is not retrieval

At this point, it's tempting to call this a complete memory system.

It isn't.

We deliberately built the simplest possible implementation.

The agent currently reads the memory file into its context.

That means:

```text
more memories
     ↓
larger MEMORY.md
     ↓
larger prompt
     ↓
more context consumption
```

There is no:

*   vector database
    
*   embeddings
    
*   semantic search
    
*   ranking
    
*   relevance scoring
    
*   memory consolidation
    
*   forgetting
    
*   deduplication
    

And that's intentional.

We're learning the underlying mechanism first.

Later, more sophisticated memory systems can be built on top of the same fundamental idea:

```text
stored information
       ↓
retrieve relevant information
       ↓
inject into model context
```

The retrieval layer is the part that becomes sophisticated.

The fundamental mechanism remains context injection.

* * *

# Memory vs session history

These two concepts are often confused.

Consider:

### Persistent memory

```text
"The production deployment uses Kubernetes."
```

That's a fact worth remembering across many conversations.

### Session history

```text
"User asked me to update deployment.yaml.
I changed line 42.
The test failed.
I was about to inspect the failure."
```

That's conversation/task state.

They have different lifetimes and different purposes.

A useful mental model is:

```text
MEMORY.md
    ↓
Long-lived facts

.agent_sessions/
    ↓
Shorter-lived conversation state
```

* * *

# Memory vs project instructions

There is another important distinction:

```text
AGENTS.md
```

is not the same as:

```text
MEMORY.md
```

Think of it this way:

```text
AGENTS.md
    = "How should you behave in this project?"

MEMORY.md
    = "What facts have been worth remembering?"

Session
    = "What were we doing?"
```

That separation becomes increasingly useful as the agent becomes more capable.

* * *

# Why not modify the system prompt manually every time?

Because the harness should own this responsibility.

The model shouldn't have to know:

```text
Where is AGENTS.md?

How do I read MEMORY.md?

How do I restore a session?

How do I construct the context?
```

Those are harness concerns.

The LLM should receive the resulting context and reason over it.

This follows the architectural principle we've been building throughout this series:

> **The model decides what to do; the harness controls the environment in which it operates.**

* * *

# How v0.8 builds on v0.7

In `v0.7`, we introduced lifecycle hooks:

```text
permission
    ↓
pre-hook
    ↓
tool
    ↓
post-hook
```

Now memory sits around the overall execution lifecycle:

```text
Persistent context
        ↓
System prompt
        ↓
       LLM
        ↓
Permission
        ↓
Pre-hook
        ↓
Tool
        ↓
Post-hook
        ↓
       LLM
        ↓
Persistent memory
```

This is becoming a real agent harness rather than a simple API wrapper.

* * *

# The complete architecture so far

After eight lessons, our agent looks like this:

```text
                       ┌────────────────────┐
                       │       Human        │
                       └─────────┬──────────┘
                                 │
                           AGENTS.md
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────┐
│                    AGENT HARNESS                         │
│                                                          │
│  ┌───────────────┐    ┌──────────────────────────────┐  │
│  │ Project       │    │ Persistent Memory            │  │
│  │ Context       │    │ MEMORY.md                    │  │
│  └───────┬───────┘    └──────────────┬───────────────┘  │
│          │                           │                  │
│          └─────────────┬─────────────┘                  │
│                        ▼                                │
│                 System Prompt                          │
│                        │                                │
│                        ▼                                │
│                       LLM                               │
│                        │                                │
│                        ▼                                │
│                 Tool Selection                          │
│                        │                                │
│                        ▼                                │
│                Permission Gate                          │
│                        │                                │
│                        ▼                                │
│                    Pre-Hook                             │
│                        │                                │
│                        ▼                                │
│                   Tool Execute                          │
│                        │                                │
│                        ▼                                │
│                   Post-Hook                             │
│                        │                                │
│                        ▼                                │
│                  Tool Result                            │
│                        │                                │
│                        ▼                                │
│                       LLM                               │
│                        │                                │
│                 ┌──────┴───────┐                        │
│                 │              │                        │
│              remember       finish                     │
│                 │              │                        │
│                 ▼              ▼                        │
│             MEMORY.md        Return                     │
│                                                          │
│        .agent_sessions/ → session resume                │
└──────────────────────────────────────────────────────────┘
```

The agent now has:

```text
Tools
Permissions
Hooks
Context
Memory
Sessions
```

We're gradually assembling the infrastructure that production coding agents need.

* * *

# The most important lesson from v0.8

The easiest mistake when learning AI agents is to think:

> "Memory must be some sophisticated AI subsystem."

Start with the fundamentals instead.

At the lowest level:

```text
Memory = persistent information + context injection
```

The simplest implementation can literally be:

```text
MEMORY.md
```

plus:

```python
read_text(...)
```

plus:

```text
system prompt
```

Everything more sophisticated—embeddings, vector stores, retrieval, summarization, ranking, consolidation—is an optimization around that fundamental mechanism.

That's exactly why this implementation is useful as a learning exercise.

* * *

# What v0.8 still doesn't solve

This implementation intentionally leaves several problems open.

### 1\. Memory can grow forever

`MEMORY.md` is append-only.

Eventually the prompt could become too large.

### 2\. Every memory is injected

The agent doesn't currently decide which memories are relevant.

### 3\. Duplicate memories are possible

Nothing prevents:

```text
Python is used.
Python is used.
Python is used.
```

from appearing multiple times.

### 4\. Memory can become stale

A remembered fact can become incorrect.

### 5\. Session history can grow

A long transcript can eventually exceed the model's context window.

And that brings us directly to the next lesson.

* * *

# What's next: context compaction

The roadmap after `v0.8-memory` is:

```text
v0.9-compaction
```

The problem is now obvious.

We've learned how to put more context into the model.

But context windows are finite.

If a conversation becomes:

```text
100 turns
500 turns
1,000 turns
```

we cannot simply keep appending everything forever.

The next architectural question is:

> **How do we keep the useful information while removing old context?**

That's the purpose of context compaction.

The agent will eventually need to summarize older conversation history so the active context remains manageable.

So the progression is becoming:

```text
v0.8
Persistent memory
       ↓
v0.9
Context compaction
       ↓
v0.10
On-demand skills
       ↓
v0.11
MCP
       ↓
v0.12
Subagents
       ↓
v0.13
Verification loop
```

Each lesson addresses a different limitation of the previous architecture.

* * *

# Series recap

We've now gone from a minimal tool-calling loop to a considerably more capable harness.

| Version | Capability |
| --- | --- |
| `v0.1` | Minimal agent loop |
| `v0.2` | Filesystem tools |
| `v0.3` | Guarded shell |
| `v0.4` | Code editing and search |
| `v0.5` | Multiple LLM providers |
| `v0.6` | Permissions |
| `v0.7` | Lifecycle hooks |
| `v0.8` | Persistent memory and sessions |
| `v0.9` | Context compaction |

The architecture is no longer just:

```text
LLM + tools
```

It is becoming:

```text
LLM
 +
Tools
 +
Permissions
 +
Hooks
 +
Context
 +
Memory
 +
Sessions
```

And that's the real goal of this series:

**understand what an agent framework is actually doing by building the pieces ourselves.**

* * *

# Key takeaway

An AI agent does not magically remember.

The harness remembers for it.

At the simplest level:

```text
             write
Agent ─────────────────► MEMORY.md
                           │
                           │
                           │ next run
                           ▼
                        read file
                           │
                           ▼
                      system prompt
                           │
                           ▼
                           LLM
```

That simple loop is the foundation of persistent agent memory.

Once you understand that mechanism, more advanced memory architectures become much easier to reason about.

\*\*Memory is not magic.

It's state.

State becomes useful when the harness puts it back into context.\*\*

* * *

## Source code

The complete implementation for this lesson is available at the `v0.8-memory` tag of the repository:

[v0.8-memory source code](https://github.com/nik-hil/agents-zero-2-hero/tree/v0.8-memory?utm_source=chatgpt.com)

The key files are:

*   `memory.py` — persistent memory and session storage
    
*   `coding_agent.py` — integration with the agent loop
    
*   `tests/test_memory.py` — offline tests
    
*   `lessons/v0.8-memory.md` — lesson specification

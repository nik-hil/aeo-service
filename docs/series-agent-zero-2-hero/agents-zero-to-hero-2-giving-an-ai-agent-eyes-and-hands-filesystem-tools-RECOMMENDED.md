# Agents Zero to Hero #2: Giving an AI Agent Eyes and Hands — Filesystem Tools

## Agents Zero to Hero #2: Giving an AI Agent Eyes and Hands — Filesystem Tools

In the previous article, we built the smallest useful AI coding agent.

It could:

*   receive a task
    
*   ask an LLM what to do
    
*   call a Python execution tool
    
*   observe the result
    
*   call `finish` when the task was complete
    

That was `v0.1-basic-tool`.

It was enough to prove the core agent loop.

But a coding agent that cannot inspect or modify files is barely a coding agent.

A real coding task looks more like:

```text
Find the project
    ↓
Inspect files
    ↓
Read source code
    ↓
Modify source code
    ↓
Run something
    ↓
Inspect result
```

So the next question is:

> What is the smallest useful filesystem interface we can give the agent?

The answer in `v0.2-new-tools` is three tools:

```text
list_files
read_file
write_file
```

Repository:

https://github.com/nik-hil/agents-zero-2-hero

* * *

# From one capability to a toolkit

At `v0.1`, the tool registry was:

```python
TOOLS = {
    "execute_code": execute_code,
    "finish": finish,
}
```

At `v0.2`, it becomes:

```python
TOOLS = {
    "execute_code": execute_code,
    "finish": finish,
    "list_files": list_files,
    "read_file": read_file,
    "write_file": write_file,
}
```

This looks like a small change.

Architecturally, it is much more important.

We are no longer teaching the model one action.

We are beginning to build a **toolkit**.

* * *

# The workspace boundary

The most important design decision in this tag is not actually the three tools.

It is the workspace.

The agent creates:

```python
WORKSPACE = Path("agent_workspace").resolve()
WORKSPACE.mkdir(exist_ok=True)
os.chdir(WORKSPACE)
```

This gives the harness a clear rule:

> File operations belong inside `agent_workspace`.

That boundary is critical.

Without it, a tool such as:

```text
read_file("/some/path")
```

could potentially expose arbitrary files on the host machine.

So we establish the first security invariant:

```text
Agent-controlled filesystem access
                ↓
        agent_workspace
                ↓
           nowhere else
```

* * *

# Path traversal protection

For every filesystem operation, the code resolves the resulting path:

```python
target = (WORKSPACE / path).resolve()
```

Then checks:

```python
if not target.is_relative_to(WORKSPACE):
    return {
        "error": "Path must be inside the workspace"
    }
```

This protects against path traversal.

For example, a model might theoretically attempt:

```text
../../etc/passwd
```

After resolution, that path would not remain inside `WORKSPACE`.

The tool therefore rejects it.

This is an important lesson for agent design:

> **Never assume the model will only generate safe arguments.**

A model is not a security boundary.

Tool implementations must enforce their own invariants.

* * *

# Tool 1: list\_files

The first new capability is:

```python
def list_files(path: str = ".") -> dict:
```

The tool resolves the requested directory:

```python
target = (WORKSPACE / path).resolve()
```

and validates it.

Then:

```python
for item in sorted(target.iterdir()):
    ...
```

The result differentiates files and directories:

```text
[DIR]  src/
[FILE] README.md
[FILE] app.py
```

The returned structure looks like:

```python
{
    "path": path,
    "items": items,
    "count": len(items)
}
```

This may seem mundane.

But it creates an important capability:

> The agent can now discover its environment.

That is the beginning of **observation**.

* * *

# Why observation matters

Consider a user request:

```text
Fix the authentication bug in this project.
```

The model cannot sensibly edit anything if it does not know what files exist.

A useful first sequence is:

```text
list_files(".")
      ↓
read_file("...")
      ↓
understand code
      ↓
modify code
```

This is why I think about tools in terms of agent capabilities rather than just functions.

A coding agent needs something resembling:

```text
eyes → inspect
hands → modify
feet → execute
```

`list_files` is part of the agent's eyes.

* * *

# Tool 2: read\_file

The next capability:

```python
def read_file(filepath: str) -> dict:
```

It again performs the workspace security check:

```python
full_path = (WORKSPACE / filepath).resolve()

if not full_path.is_relative_to(WORKSPACE):
    return {
        "error": "Path must be inside workspace"
    }
```

Then:

```python
if not full_path.is_file():
    return {
        "error": f"Not a file or does not exist: {filepath}"
    }
```

Finally:

```python
content = full_path.read_text(encoding="utf-8")
```

and returns:

```python
{
    "filepath": filepath,
    "content": content,
    "length": len(content)
}
```

Now the model can inspect actual source code.

This changes the nature of the agent.

At `v0.1`:

```text
task → compute → answer
```

At `v0.2`:

```text
task
  ↓
inspect environment
  ↓
read information
  ↓
reason
  ↓
take action
```

That is much closer to real agent behavior.

* * *

# Tool 3: write\_file

The third capability is:

```python
def write_file(
    filepath: str,
    content: str,
    mode: str = "w"
) -> dict:
```

Two modes are supported:

```text
w → overwrite
a → append
```

The implementation validates the mode:

```python
if mode not in ("w", "a"):
    return {
        "error": 'mode must be "w" or "a"'
    }
```

Then validates the path.

It also creates missing directories:

```python
full_path.parent.mkdir(
    parents=True,
    exist_ok=True
)
```

Finally:

```python
with open(
    full_path,
    mode=mode,
    encoding="utf-8"
) as f:
    f.write(content)
```

The tool reports what happened:

```python
{
    "filepath": filepath,
    "action": "overwritten",
    "bytes_written": len(content)
}
```

* * *

# Why not just give the model Python again?

A natural question is:

> We already have `execute_code`. Couldn't the model just use Python to read and write files?

Technically, yes.

Architecturally, that would be a bad direction.

A tool such as:

```text
read_file(path)
```

gives us a controlled semantic capability.

Compare that with:

```python
execute_code("""
open('/some/path').read()
""")
```

The latter is much harder to reason about, validate, audit, and secure.

Explicit tools let us define boundaries.

For example:

```text
read_file
 ├── allowed workspace
 ├── known input
 └── controlled output
```

versus:

```text
execute_code
 └── potentially arbitrary behavior
```

This distinction becomes extremely important as the harness grows.

* * *

# Tool schemas evolve too

Adding Python functions is only half of the implementation.

The model must also be told that the tools exist.

For example:

```python
{
    "type": "function",
    "function": {
        "name": "read_file",
        "description":
            "Read the full content of a file in the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description":
                        "Relative path to the file"
                }
            },
            "required": ["filepath"]
        }
    }
}
```

The system therefore has two representations of every capability:

```text
Python implementation
        +
LLM-facing tool schema
```

The schema's `read_file` name corresponds to the `"read_file"` entry in `TOOLS`, which points to the Python function. The model requests that named tool with a `filepath` argument; the harness runs the registered implementation, where the workspace checks and file read happen.

This pattern will continue throughout the project.

* * *
# The agent prompt also changes

The system prompt now tells the model about the environment:

```text
You are an autonomous coding agent working inside a
dedicated workspace folder.

Available tools:
- list_files(path=".")
- read_file(filepath)
- write_file(filepath, content, mode="w")
- execute_code(code)
- finish(answer)
```

It also introduces some behavioral rules:

```text
- ALWAYS explore the workspace first with list_files
- Use relative paths only
- Read files before trying to modify or understand them
- Think step by step
- Call finish() when completely solved
```

This is an early example of something that becomes central to agent engineering:

> **The tool implementation defines what the agent can do. The system prompt defines how the agent should use those capabilities.**

* * *

# An important observation about agent design

It is tempting to think:

```text
more tools = better agent
```

That is not necessarily true.

Every additional tool increases:

*   model decision complexity
    
*   tool-selection ambiguity
    
*   prompt size
    
*   attack surface
    
*   validation requirements
    
*   permission complexity
    

The goal is not to expose every possible API.

The goal is to expose **useful primitives with clear boundaries**.

At this point, three filesystem operations are enough:

```text
discover
read
write
```

* * *

# What does a real interaction look like?

Suppose the user asks:

```text
Create a Python script called hello.py that prints Hello World,
then execute it and return the output.
```

The model can now reason through something like:

```text
list_files(".")
        ↓
understand workspace
        ↓
write_file("hello.py", ...)
        ↓
execute_code(...)
        ↓
observe output
        ↓
finish(...)
```

That is already a genuine agent loop.

The harness is effectively coordinating:

```text
Observation
    ↓
Reasoning
    ↓
Action
    ↓
Observation
    ↓
Reasoning
    ↓
Action
```

This recurring cycle is one of the fundamental patterns behind agentic systems.

* * *

# Why the workspace matters even more for coding agents

The repository deliberately does not let these tools freely operate over the user's entire filesystem.

Instead:

```text
machine
└── agent_workspace
    ├── source.py
    ├── tests/
    └── README.md
```

The model sees and modifies this controlled region.

That gives us a natural place to introduce future protections:

```text
workspace
permissions
sandbox
resource limits
audit logs
```

This is much easier than trying to bolt security onto unrestricted system access after the fact.

* * *

# A subtle lesson: the model is not trusted

This is perhaps the most important lesson from `v0.2`.

The model might generate:

```text
read_file("../../secret.txt")
```

The tool must reject it.

The model might generate:

```text
write_file("/etc/hosts", ...)
```

The tool must reject it.

The model might hallucinate:

```text
read_file("missing.py")
```

The tool should return a structured error.

The model then gets the result and can recover.

That gives us a general design principle:

> **The harness should make invalid actions safe and recoverable whenever possible.**

* * *

# Error handling is part of agent intelligence

Notice that the tools return dictionaries such as:

```python
{
    "error": "File does not exist"
}
```

rather than simply crashing.

Why?

Because an error can become an observation.

For example:

```text
Agent:
read_file("config.py")

Tool:
{
    "error": "Not a file or does not exist"
}
```

The agent can now decide:

```text
Maybe the file is elsewhere.
Let's inspect the directory.
```

This is very different from treating exceptions as terminal failures.

For agents:

```text
error → observation → next decision
```

is often better than:

```text
error → crash
```

* * *

# Running v0.2

Checkout the tag:

```bash
git checkout v0.2-new-tools
```

Then:

```bash
python coding_agent.py
```

The demo exercises:

```text
list_files
write_file
read_file
execute_code
```

and combines them into multi-step tasks.

* * *

# What changed architecturally?

The first checkpoint was:

```text
LLM
 +
execute_code
 +
finish
```

The second becomes:

```text
                ┌──────────────┐
                │     LLM      │
                └──────┬───────┘
                       │
                ┌──────▼───────┐
                │    Tools     │
                ├──────────────┤
                │ list_files   │
                │ read_file    │
                │ write_file   │
                │ execute_code │
                │ finish       │
                └──────┬───────┘
                       │
                ┌──────▼───────┐
                │   Workspace  │
                └──────────────┘
```

We have now added an **environment** to our agent.

The agent is no longer just computing.

It can observe and modify state.

* * *

# The problem we have now

Our agent can manipulate files.

It can also execute Python.

But real coding workflows depend heavily on shell commands.

Think about:

```text
git status
git diff
pytest
grep
find
ls -la
python -m ...
```

We could keep adding specialized tools:

```text
git_tool
test_tool
grep_tool
find_tool
...
```

That quickly becomes unwieldy.

The obvious next step is:

> Give the agent a shell.

But there is an immediate problem.

Giving an AI agent unrestricted shell access is a terrible idea.

So the next checkpoint asks a much more interesting question:

> **How do we give an agent a shell without giving it the whole machine?**

That is `v0.3`.

* * *

## Repository

https://github.com/nik-hil/agents-zero-2-hero

Tag:

```text
v0.2-new-tools
```

Next:

```text
v0.3-bash-tut
```

From here, the project starts moving from a toy tool-calling demo toward the foundations of a real coding-agent harness.

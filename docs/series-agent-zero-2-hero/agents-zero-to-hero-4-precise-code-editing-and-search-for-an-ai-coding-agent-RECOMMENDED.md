# Agents Zero to Hero #4: Precise Code Editing and Search for an AI Coding Agent

## Agents Zero to Hero #4: Precise Code Editing and Search for an AI Coding Agent

Our agent can now do quite a lot.

By the end of `v0.3`, it can:

```text
read files
write files
execute Python
run selected shell commands
operate inside a workspace
run inside a container
```

But there is still a major weakness.

The agent's file modification primitive is:

```text
write_file()
```

That means the model generally has to provide the new contents of an entire file.

For real software engineering, that's clumsy.

Imagine a 1,000-line file where you need to change:

```python
timeout = 10
```

to:

```python
timeout = 30
```

Rewriting the entire file is unnecessary.

A human developer would search for the code and make a targeted edit.

So the next milestone is:

```text
v0.4-edit-tool
```

with two new capabilities:

```text
edit_file
code_search
```

This article is about why those two primitives matter and how they fit into the agent-harness architecture.

Repository:

https://github.com/nik-hil/agents-zero-2-hero

* * *

# The evolution of the toolkit

At this point, the toolkit looks roughly like:

```text
execute_code
finish

list_files
read_file
write_file

bash
```

We're now adding:

```text
edit_file
code_search
```

The conceptual toolbox becomes:

```text
Observe:
    list_files
    read_file
    code_search

Modify:
    write_file
    edit_file

Execute:
    execute_code
    bash

Control:
    finish
```

That categorization is useful because it starts making the harness's capabilities explicit.

* * *

# Why `write_file` is not enough

Let's say the agent sees:

```python
def calculate_total(items):
    return sum(items)
```

and the user asks:

```text
Add logging before calculating the total.
```

With `write_file`, the model has to reconstruct the surrounding file and submit the replacement contents.

This can cause:

```text
unrelated code changes
formatting changes
accidental deletions
large prompts
token waste
```

A targeted edit is much better.

* * *

# Introducing edit\_file

The new primitive is:

```python
def edit_file(
    filepath: str,
    search_text: str,
    replace_text: str
) -> dict:
```

The contract is straightforward:

```text
search_text
    ↓
find exact existing text

replace_text
    ↓
replace it
```

The implementation first validates the path:

```python
full_path = (
    WORKSPACE / filepath
).resolve()

if not full_path.is_relative_to(WORKSPACE):
    return {
        "error":
        "Path must be inside workspace"
    }
```

Then confirms the file exists:

```python
if not full_path.is_file():
    return {
        "error":
        f"File does not exist: {filepath}"
    }
```

* * *

# Exact matching

The interesting part is:

```python
original_content = full_path.read_text(
    encoding="utf-8"
)

if search_text not in original_content:
    return {
        "error":
            "search_text not found in the file",
        ...
    }
```

Then:

```python
updated_content = original_content.replace(
    search_text,
    replace_text,
    1
)
```

Notice the final argument:

```python
1
```

Only the first occurrence is replaced.

That is intentional.

For an agent tool, predictability matters.

A command that silently changes five matching regions might be much worse than a command that changes one explicitly requested region.

* * *

# Why exact search-and-replace?

There are many possible editing strategies.

For example:

```text
whole-file replacement
line-number replacement
AST transformations
regex replacement
diff application
search-and-replace
```

This project chooses exact text replacement because it makes the mechanism easy to understand.

The model provides:

```text
old block
new block
```

and the harness performs exactly one replacement.

The simplicity is useful for learning.

* * *

# Edit tools are also model-friendly

Consider the difference between these prompts.

### Whole-file editing

```text
Rewrite this 800-line file with the following change...
```

versus:

### Targeted editing

```text
Replace:

def timeout():
    return 10

with:

def timeout():
    return 30
```

The second operation requires much less generated content.

That has benefits in:

```text
token usage
latency
error probability
reviewability
```

and potentially agent reliability.

* * *

# But exact editing has a trade-off

There is an important limitation.

The model must provide the exact text:

```text
search_text
```

including indentation and formatting.

The tool explicitly documents that the match needs to be exact.

So if the file contains:

```python
return value
```

but the model sends:

```python
return value\n
```

or slightly different whitespace, the operation may fail.

That failure is not necessarily bad.

A precise failure is safer than a fuzzy edit.

The agent can then read the file again and retry.

This gives us:

```text
failed edit
    ↓
observation
    ↓
correct search block
    ↓
retry
```

which is exactly what we want from an agent loop.

* * *

# code\_search

The second new capability is:

```python
def code_search(
    pattern: str,
    file_pattern: str = "*.py",
    context_lines: int = 2
) -> dict:
```

This gives the agent a way to locate relevant code before editing.

That sounds simple.

It is actually a major capability.

* * *

# Why code search changes the workflow

Before `code_search`, the agent's approach might be:

```text
list files
↓
guess which file
↓
read file
↓
search mentally
```

Now it can do:

```text
code_search("timeout")
        ↓
identify likely files
        ↓
read_file(...)
        ↓
edit_file(...)
```

That is a much more efficient coding workflow.

* * *

# ripgrep first

The implementation first checks:

```python
rg_available = shutil.which("rg") is not None
```

If `ripgrep` exists, it builds a command:

```python
cmd = [
    "rg",
    "--color=never",
    f"--context={context_lines}",
    "--glob",
    file_pattern,
    pattern,
    ".",
]
```

and executes it inside the workspace.

This gives us a fast code-search primitive.

* * *

# Why ripgrep?

For a coding agent, source-code search happens constantly.

Typical queries look like:

```text
find function X
find error message Y
find configuration Z
find references to class A
find TODO
```

A fast repository search tool therefore becomes one of the highest-value primitives an agent can have.

And instead of inventing a complicated search engine, the project uses an existing developer tool:

```text
ripgrep
```

This is another good lesson:

> Agent tools don't always need to be custom technology. They often need to be good interfaces over existing developer primitives.

* * *

# The Python fallback

What happens if `rg` isn't installed?

The tool falls back to Python:

```python
for file_path in WORKSPACE.rglob(file_pattern):
    ...
```

It reads each matching file:

```python
content = file_path.read_text(
    encoding="utf-8",
    errors="ignore"
)
```

then scans the lines:

```python
for i, line in enumerate(lines):
    if pattern in line:
        ...
```

This is a simple fallback, but it demonstrates a useful architectural principle:

```text
capability
    ↓
preferred implementation
    ↓
portable fallback
```

The external behavior remains:

```text
code_search(...)
```

even though its internal implementation can vary.

* * *

# Returning context

When the search finds a match, it captures nearby lines.

For example:

```text
line N - 2
line N - 1
MATCH
line N + 1
line N + 2
```

That is why the API exposes:

```python
context_lines: int = 2
```

Context matters because a search result without surrounding code can be difficult for a model to interpret.

The agent doesn't just need:

```text
line 73 matched
```

It needs enough context to understand what line 73 means.

* * *

# Observation gets more powerful

At `v0.2`, the agent had:

```text
list_files
read_file
```

Now observation becomes:

```text
list_files
read_file
code_search
```

This is an important progression.

A useful agent environment isn't merely a set of action tools.

It also needs **information retrieval tools**.

The agent's effectiveness is bounded by how well it can observe the state of the environment.

* * *

# Editing plus searching

The two new tools are particularly powerful together.

A typical coding workflow becomes:

```text
code_search("retry")
       ↓
read_file("client.py")
       ↓
edit_file(
    "client.py",
    old_block,
    new_block
)
       ↓
execute_code(...)
```

Reading before editing matters because `old_block` must match the file's actual text, including indentation and formatting. After execution, the workflow still includes verification: search → inspect → edit → execute → verify, not just finding and replacing text.

This is increasingly close to what a developer does manually.

* * *
# The harness is becoming an environment

The architecture now looks like:

```text
                      ┌─────────────┐
                      │     LLM     │
                      └──────┬──────┘
                             │
                        decisions
                             │
                  ┌──────────▼──────────┐
                  │       Harness       │
                  ├─────────────────────┤
                  │ list_files           │
                  │ read_file            │
                  │ code_search          │
                  │ write_file           │
                  │ edit_file            │
                  │ execute_code         │
                  │ bash                 │
                  │ finish               │
                  └──────────┬──────────┘
                             │
                             ▼
                       Workspace
```

The model now has:

```text
eyes
hands
execution
```

This is why I find the word **harness** useful.

The LLM itself hasn't become magical.

We've progressively surrounded it with capabilities.

* * *

# An important architectural distinction

We now have two separate concerns:

### Model intelligence

```text
What should I do next?
```

### Harness mechanics

```text
How do I safely perform that action?
```

This separation should remain intact.

For example:

```text
LLM:
code_search("timeout")

Harness:
run ripgrep
validate workspace
capture output
return result
```

The model determines intent.

The harness handles execution.

This distinction will become critical once we start adding permissions.

* * *

# Why precise editing is safer than broad rewriting

Suppose a model receives:

```text
Fix the timeout bug.
```

and rewrites a 600-line file.

Even if the intended change was correct, we now have a huge surface area for unintended modifications.

With targeted edits:

```text
search block
    ↓
replacement block
```

we can reduce the size of the mutation.

That makes the agent easier to reason about and potentially easier to review.

In other words:

> **The more powerful the agent becomes, the more important small, explicit mutations become.**

* * *

# This also reduces token usage

There is another practical advantage.

Suppose a file contains 10,000 tokens.

A whole-file rewrite requires the model to produce a large output.

An exact edit might require:

```text
20 tokens old block
+
25 tokens new block
```

That is dramatically cheaper.

So tool design affects not only correctness and safety, but also:

```text
latency
cost
context consumption
```

* * *

# Where the project is now

Let's look at the evolution.

### v0.1

```text
Reason → execute Python → finish
```

### v0.2

```text
Explore → read → write → execute → finish
```

### v0.3

```text
Explore → read → write → execute → shell → finish
                ↑
           container
```

### v0.4

```text
Search → inspect → edit → execute → verify
```

That is beginning to resemble a real coding agent.

* * *

# But we have another problem

There is now a growing number of tools:

```text
execute_code
finish
list_files
read_file
write_file
bash
edit_file
code_search
```

And every tool represents a capability.

Who decides whether that capability is allowed?

Right now, permissions are distributed across individual implementations:

```text
bash → command allowlist
file tools → workspace checks
```

That approach won't scale. To understand what the agent is allowed to do across the growing toolkit, we have to examine rules scattered across individual tool implementations.

What we really want is a central policy layer—a shared permission decision before tool execution:

```text
Tool call
   ↓
Permission checker
   ↓
allowed?
   ├── yes → execute
   └── no  → reject / ask
```

That is a much more general model.

And it leads to the next major architectural step.

* * *
# The next step: permissions

The repository roadmap calls the next governance milestone:

```text
PermissionChecker
```

with concepts such as:

```text
ask
auto
plan
path rules
command rules
denied commands
```

That is where our simple bash allowlist starts evolving into a real **governance layer** around the agent.

The important transition is:

```text
tool-level safety
        ↓
centralized permission model
```

That is one of the most important architectural transitions in the entire series.

* * *

## Repository

https://github.com/nik-hil/agents-zero-2-hero

Tag:

```text
v0.4-edit-tool
```

Next:

```text
v0.5
```

At that point, the question stops being:

> What can the agent do?

and becomes:

> **What is the agent allowed to do?**

That is where an agent starts becoming a system rather than just a collection of tools.

# Agents Zero to Hero #6: Teaching an AI Agent When It Is Allowed to Act

## Agents Zero to Hero #6: Teaching an AI Agent When It Is Allowed to Act

An AI coding agent becomes significantly more useful when it can read files, edit code, execute Python, run shell commands, and search a codebase.

But there is a problem.

**Who decides whether the agent is actually allowed to perform an action?**

Until now, in this series, the answer was effectively:

> If the model asks for the tool, execute the tool.

That is fine while building a toy agent.

It is not a good security model for a real agent.

In this iteration of **Agents Zero to Hero**, I am adding a permission layer to the agent harness.

The goal is simple:

> **The LLM decides what it wants to do. The agent harness decides whether it is allowed to do it.**

This is the key architectural idea introduced in `v0.6-permissions`.

* * *

## What is an AI agent permission layer?

An AI agent permission layer is a control mechanism that evaluates a tool call before the tool is actually executed.

For example, suppose the model generates:

```text
write_file("config.yaml", "...")
```

The LLM has requested an action.

The harness should not immediately execute it.

Instead, the request goes through a permission check:

```text
LLM
 │
 │ tool call
 ▼
PermissionChecker
 │
 ├── hard security rules
 ├── path rules
 ├── command rules
 └── permission mode
 │
 ├── ALLOW
 └── DENY
 │
 ▼
Tool execution
```

This creates an important separation of responsibilities.

The **model proposes an action**.

The **harness enforces policy**.

* * *

# Why does an AI agent need permissions?

Consider the tools our agent has accumulated.

By this point, it can:

*   list files
    
*   read files
    
*   write files
    
*   edit files
    
*   execute Python
    
*   execute shell commands
    
*   search source code
    

Some of these operations are fundamentally different from others.

Reading a file:

```text
read_file("README.md")
```

doesn't normally change state.

Writing a file:

```text
write_file("README.md", "new content")
```

does.

Running Python:

```text
execute_code("import os; ...")
```

could potentially have much broader consequences.

Running a shell command is even more interesting:

```text
bash("...")
```

because the command itself may contain destructive operations.

So the harness needs to understand the difference between:

```text
observation
```

and

```text
mutation
```

That distinction is what the permission layer formalizes.

* * *

# The architecture before v0.6

Before this change, the agent loop was essentially:

```text
User
  │
  ▼
LLM
  │
  │ tool call
  ▼
Tool
  │
  ▼
Result
  │
  ▼
LLM
```

The model had access to the tools exposed by the harness.

The tool implementations themselves contained some security controls.

For example, earlier versions already restricted filesystem operations to the agent workspace, and the `bash` tool had an allowlist and `shell=False`.

Those controls are still useful.

But they are **tool-specific controls**.

What was missing was a centralized policy layer.

* * *

# Introducing PermissionChecker

The new `permissions.py` introduces a `PermissionChecker`.

The design is intentionally small:

```python
@dataclass
class PermissionChecker:
    mode: Mode = Mode.AUTO
    denied_commands: list[str] = field(
        default_factory=lambda: list(DEFAULT_DENIED_COMMANDS)
    )
    path_rules: list[tuple[str, bool]] = field(default_factory=list)
    approver: callable = _always_deny
```

The checker receives:

```text
tool name
+
tool arguments
```

and produces a `Decision`.

```python
@dataclass
class Decision:
    allowed: bool
    reason: str = ""
```

So permission checking becomes a pure question:

```text
Can this tool call execute?
```

rather than mixing policy decisions into every individual tool.

* * *

# The three permission modes

The most visible feature in `v0.6` is the introduction of three permission modes:

```text
auto
default
plan
```

They represent three different levels of trust.

## 1\. Auto mode

In `auto` mode, mutating tools are allowed.

Conceptually:

```text
read       → ALLOW
write      → ALLOW
edit       → ALLOW
execute    → ALLOW
bash       → ALLOW
```

This is useful for:

*   trusted environments
    
*   sandboxed execution
    
*   automated runs
    
*   development and experimentation
    

The important detail is that **auto does not mean bypass all security**.

Hard deny rules still apply.

The implementation explicitly evaluates command and path rules before the mode decision.

So:

```text
auto
  ≠
no security
```

Instead:

```text
auto
=
no interactive approval for otherwise permitted mutations
```

* * *

# 2\. Default mode

`default` is designed for normal interactive usage.

Read-only operations are allowed automatically.

Mutating operations require approval.

For example:

```text
read_file("README.md")
```

can execute immediately.

But:

```text
write_file("README.md", "...")
```

requires approval.

The default CLI approver asks:

```text
[permission] allow write_file({...})? [y/N]
```

The user can then explicitly allow or deny the action.

This creates a human-in-the-loop boundary.

* * *

# 3\. Plan mode

The third mode is `plan`.

Plan mode allows observation but prevents mutations.

Conceptually:

```text
list_files     → ALLOW
read_file      → ALLOW
code_search    → ALLOW
finish         → ALLOW

write_file     → BLOCK
edit_file      → BLOCK
execute_code   → BLOCK
bash           → BLOCK
```

This is useful when you want the agent to inspect a repository and reason about what it would change without actually changing anything.

That is a very useful primitive for a future planning workflow.

* * *

# Read-only versus mutating tools

The permission layer explicitly defines read-only tools:

```python
READ_ONLY_TOOLS = {
    "list_files",
    "read_file",
    "code_search",
    "finish",
}
```

Everything else is treated as potentially mutating.

Read-only does not mean exempt from policy: hard security rules and path rules are checked first. Only calls that pass those checks reach this classification:

```text
                Tools
                  │
       ┌──────────┴──────────┐
       │                     │
   Read-only              Mutating
       │                     │
       ▼                     ▼
     Allow             Permission mode
                              │
                    ┌─────────┼─────────┐
                    │         │         │
                   auto    default     plan
                    │         │         │
                  allow      ask       deny
```

This classification is simple, but it establishes a foundation that can become much more sophisticated later.

* * *
# Hard security rules come first

One of the most important details in this implementation is the order in which permission checks happen.

The checker first evaluates hard rules.

That means certain operations can be denied regardless of permission mode.

For example, the default denied command list contains patterns such as:

```python
DEFAULT_DENIED_COMMANDS = [
    "rm -rf",
    "rm -fr",
    "mkfs",
    "dd if=",
    ":(){",
    "shutdown",
    "reboot",
    "shutil.rmtree",
    "os.system",
    "> /dev/",
]
```

The exact list is deliberately small because this is a learning project, not a production security policy.

The architectural idea is more important:

> **A permission mode should not be able to override a hard security rule.**

So even:

```text
mode = auto
```

does not automatically mean:

```text
everything is allowed
```

The flow is:

```text
Tool call
   │
   ▼
Hard security rules
   │
   ├── blocked → DENY
   │
   ▼
Path rules
   │
   ├── blocked → DENY
   │
   ▼
Read-only?
   │
   ├── yes → ALLOW
   │
   ▼
Permission mode
```

That ordering is important.

* * *

# Path-based permissions

The permission layer also introduces path rules.

The configuration looks like:

```python
path_rules = [
    ("*.env", False)
]
```

This means:

> Deny tool calls targeting files matching `*.env`.

The checker uses `fnmatch` for matching.

For example:

```text
.env
production.env
database.env
```

can all be protected by a rule such as:

```text
*.env
```

This is useful because filesystem access isn't only about *whether* the agent can write.

Sometimes the important question is:

> **Where is the agent allowed to write?**

That gives us another dimension of authorization:

```text
tool permission
+
path permission
```

* * *

# Command-based permissions

The same idea applies to executable text.

The implementation maps:

```python
TEXT_ARG = {
    "bash": "command",
    "execute_code": "code",
}
```

So the checker knows which argument contains executable content.

For example:

```python
bash(
    "rm -rf something"
)
```

can be inspected before the `bash` implementation runs.

Likewise:

```python
execute_code(
    "import os; os.system(...)"
)
```

can be evaluated against denied command phrases.

This is a useful lesson about tool design.

A permission system needs to understand the **shape of tool arguments**.

It isn't enough to know:

```text
tool = bash
```

You also need to inspect:

```text
command = "..."
```

* * *

# The most important change: gate the tool call

This is where the permission layer becomes part of the actual agent harness.

The model produces a tool call:

```python
tool_name = tool_call.function.name
args = json.loads(tool_call.function.arguments)
```

Instead of immediately executing:

```python
result = TOOLS[tool_name](**args)
```

the agent now does:

```python
decision = permissions.check(tool_name, args)
```

Only if the decision is positive does the tool execute.

Conceptually:

```python
decision = permissions.check(tool_name, args)

if not decision.allowed:
    result = {
        "error": "permission denied",
        "reason": decision.reason,
    }
else:
    result = TOOLS[tool_name](**args)
```

This is the architectural boundary we were missing in previous versions.

* * *

# Why return "permission denied" to the model?

There is another subtle but important design decision here.

A denied tool call does **not** crash the agent.

Instead, the harness returns a structured observation:

```json
{
  "error": "permission denied",
  "reason": "..."
}
```

The result goes back into the model's conversation.

That means the model can adapt.

For example:

```text
Agent:
I need to modify config.yaml.

Harness:
permission denied:
plan mode forbids mutating tool 'write_file'

Agent:
I cannot modify the file in the current permission mode.
I will inspect the existing configuration instead.
```

This is much better than treating authorization failure as an application crash.

The permission layer becomes part of the agent's environment.

* * *

# The LLM should not be the security boundary

This is perhaps the biggest lesson from this iteration.

An LLM can be instructed:

```text
Never delete files.
Never access secrets.
Never execute dangerous commands.
```

But a system should not depend exclusively on the model following those instructions.

The model is the **decision-making component**.

The harness is the **enforcement component**.

That gives us:

```text
                 AI Agent
                    │
          ┌─────────┴─────────┐
          │                   │
       LLM/model          Harness
          │                   │
   proposes actions      enforces policy
          │                   │
          └─────────┬─────────┘
                    │
                  Tools
```

The distinction is fundamental.

A prompt says:

> Don't do X.

A permission layer says:

> Even if you ask to do X, the execution layer will reject it.

Those are very different guarantees.

* * *

# Permission checks should happen before side effects

The placement of the permission check matters.

Bad:

```python
result = TOOLS[tool_name](**args)

decision = permissions.check(tool_name, args)
```

At that point the side effect has already happened.

Too late.

Correct:

```python
decision = permissions.check(tool_name, args)

if decision.allowed:
    result = TOOLS[tool_name](**args)
```

The authorization decision must happen **before the side effect**.

This pattern should become second nature when designing agent tool systems:

```text
request
  ↓
validate
  ↓
authorize
  ↓
execute
  ↓
observe
```

Not:

```text
request
  ↓
execute
  ↓
oops, should we have allowed that?
```

* * *

# A complete tool execution pipeline

After `v0.6`, our agent loop is becoming much closer to the architecture of a real agent harness.

The complete flow is now:

```text
                  User task
                      │
                      ▼
                   LLM call
                      │
                      ▼
                 Tool request
                      │
                      ▼
             Parse tool arguments
                      │
                      ▼
              PermissionChecker
                      │
          ┌───────────┴───────────┐
          │                       │
       DENIED                   ALLOWED
          │                       │
          ▼                       ▼
  Structured error           Execute tool
          │                       │
          └───────────┬───────────┘
                      │
                      ▼
                Tool observation
                      │
                      ▼
                     LLM
                      │
                 ┌────┴────┐
                 │         │
              continue   finish
```

This is the core agent loop becoming more sophisticated without becoming much more complicated.

* * *

# Configuring the permission mode

The mode is selected using an environment variable:

```text
AGENT_PERMISSION_MODE
```

with supported values:

```text
auto
default
plan
```

For example:

```bash
AGENT_PERMISSION_MODE=plan python coding_agent.py
```

Or:

```bash
AGENT_PERMISSION_MODE=default python coding_agent.py
```

Or:

```bash
AGENT_PERMISSION_MODE=auto python coding_agent.py
```

The agent reads this configuration when constructing the permission checker.

```python
permissions = PermissionChecker(
    mode=os.getenv("AGENT_PERMISSION_MODE", "auto"),
    approver=cli_approver,
)
```

That also means the permission mechanism is not hardcoded into the agent's business logic.

The policy can be configured externally.

* * *

# A simple experiment

The example task in this tag deliberately writes a file:

```text
Create a file called notes.txt containing the text
'hello from the agent', then finish.
```

This makes the permission behavior easy to observe.

## Auto mode

```text
AGENT_PERMISSION_MODE=auto
```

The write is allowed.

Expected:

```text
notes.txt created? True
```

## Plan mode

```text
AGENT_PERMISSION_MODE=plan
```

The model can inspect the workspace, but the write is blocked.

Expected:

```text
notes.txt created? False
```

## Default mode

```text
AGENT_PERMISSION_MODE=default
```

The harness asks for approval before executing the mutation.

This small experiment demonstrates something important:

> **The same agent and the same task can have different capabilities depending on the harness policy.**

The model doesn't need to change.

The tool implementation doesn't need to change.

Only the authorization policy changes.

* * *

# Permission systems are more than security

At first glance, permissions look like a security feature.

They are.

But they also enable different **agent operating modes**.

For example:

### Autonomous execution

```text
auto
```

Useful when the environment is trusted and isolated.

### Human-in-the-loop execution

```text
default
```

Useful when potentially destructive actions should require approval.

### Planning / dry-run

```text
plan
```

Useful when the agent should inspect and reason without modifying the environment.

This suggests an interesting future direction.

The permission layer can become part of the **agent UX**.

A coding agent could eventually expose:

```text
Auto
Ask
Plan
```

as user-selectable execution modes.

* * *

# What this changes architecturally

Let's compare the architecture across the series.

### v0.1

```text
LLM → tools
```

The basic tool-calling loop.

### v0.2

```text
LLM → filesystem tools
```

The agent gains workspace awareness.

### v0.3

```text
LLM → shell
```

The agent gains command execution.

### v0.4

```text
LLM → edit/search tools
```

The agent becomes much better at manipulating source code.

### v0.5

```text
LLM
 ↓
provider abstraction
 ↓
OpenRouter / DigitalOcean
```

The harness becomes independent of a particular LLM provider.

### v0.6

```text
LLM
 ↓
tool call
 ↓
Permission Layer
 ↓
tool
```

The harness now controls whether the model's requested action can actually happen.

That is a significant architectural milestone.

* * *

# A useful mental model: capability versus authorization

There are now two separate questions.

## Capability

> What can the agent potentially do?

For example:

```text
read files
write files
edit files
execute Python
run commands
search code
```

## Authorization

> What is the agent currently allowed to do?

For example:

```text
read files      → allowed
write files     → ask
execute code    → blocked
bash            → blocked
```

This distinction is extremely useful when designing AI agents.

Adding a tool gives the agent a **capability**.

The permission system determines whether that capability can be exercised in a particular context.

* * *

# Why centralization matters

Without a central permission layer, every tool needs its own authorization logic.

You might end up with:

```python
write_file():
    check_permission()

edit_file():
    check_permission()

bash():
    check_permission()

execute_code():
    check_permission()
```

This quickly becomes difficult to reason about.

Instead, the harness can enforce:

```python
for tool_call in tool_calls:
    decision = permissions.check(...)
    
    if decision.allowed:
        execute(...)
```

Now authorization is a cross-cutting concern implemented once.

This also makes future changes easier.

For example, adding:

```text
delete_file
```

should not require inventing a completely new authorization mechanism.

The tool can simply participate in the existing policy model.

* * *

# But is this production-grade security?

No.

And that's an important distinction.

This repository is intentionally a learning project.

The permission layer demonstrates the architecture and core mechanics.

A production agent would need much stronger controls, potentially including:

*   OS-level sandboxing
    
*   containers or microVMs
    
*   filesystem isolation
    
*   process isolation
    
*   network restrictions
    
*   secret isolation
    
*   resource limits
    
*   syscall restrictions
    
*   stronger command parsing
    
*   structured command policies
    
*   audit logging
    
*   identity-aware authorization
    
*   capability-based access
    
*   approval workflows
    
*   policy versioning
    

A string denylist such as:

```python
"rm -rf"
```

is not a complete security boundary.

For example, dangerous behavior can often be expressed in many different ways.

So the lesson here is not:

> "A few string checks make an AI agent secure."

The lesson is:

> **Authorization should exist as a distinct layer between model intent and tool execution.**

The actual enforcement mechanisms can become increasingly sophisticated later.

* * *

# The deeper agent-harness lesson

This series started with a simple question:

> What is an AI agent?

The answer is becoming clearer with every tag.

An LLM by itself is not a coding agent.

The model provides reasoning and decision-making.

The harness provides:

*   tools
    
*   state
    
*   observations
    
*   execution
    
*   boundaries
    
*   permissions
    

So a useful mental model is:

```text
AI Agent
=
LLM
+
Tools
+
Environment
+
Observation
+
Control
+
Permissions
```

And `v0.6` adds an important part of that equation:

```text
Control
```

The model can propose an action.

The harness decides whether that action crosses an allowed boundary.

* * *

# What I learned from v0.6

The biggest lesson for me was that **tool calling and tool authorization are two different problems**.

It is relatively easy to expose a function to an LLM:

```text
write_file(...)
```

The harder question is:

```text
Should this particular invocation be allowed?
```

And that question becomes even more important as an agent gains more capabilities.

A useful design principle emerges:

> **Never confuse the model's ability to request an action with its authority to perform that action.**

The permission layer gives the harness that authority.

* * *

# Where do we go from here?

Our agent can now:

*   inspect a workspace
    
*   read files
    
*   create files
    
*   edit files
    
*   search code
    
*   execute Python
    
*   run constrained shell commands
    
*   switch between LLM providers
    
*   enforce permission policies
    

But another problem is becoming obvious.

The agent currently receives everything through the conversation history.

As tasks become longer, the context will grow.

Eventually, we will need to answer questions such as:

*   What information should the agent remember?
    
*   What should survive between runs?
    
*   How do we persist useful knowledge?
    
*   How do we prevent the context window from growing indefinitely?
    
*   How should an agent retrieve relevant previous information?
    

That's where the next stage of the journey gets interesting.

The next capabilities will move beyond simply **giving the agent tools** toward giving the agent a more durable **context and memory architecture**.

And that is where an AI agent starts becoming more than a loop around an LLM.

* * *

## The series so far

This is **Part 6** of my *Agents Zero to Hero* series, where I am building an AI coding-agent harness from first principles, one Git tag at a time.

1.  **v0.1 — Tool Calling** Build the basic LLM → tool → observation loop.
    
2.  **v0.2 — Filesystem Tools** Give the agent the ability to explore and modify a workspace.
    
3.  **v0.3 — Shell Execution** Give the agent controlled command execution.
    
4.  **v0.4 — Code Editing and Search** Give the agent better primitives for navigating and modifying source code.
    
5.  **v0.5 — Multiple LLM Providers** Separate the agent harness from the underlying model provider.
    
6.  **v0.6 — Permissions** Introduce authorization between model intent and tool execution.
    

The repository contains the complete implementation for each checkpoint as a Git tag, so the idea is to read the code incrementally rather than starting with a large agent framework and trying to understand everything at once.

The goal is not to build the most sophisticated agent.

The goal is to understand **why an agent harness needs each piece and what problem that piece actually solves.**

* * *

## Key takeaway

An AI agent should not directly translate model output into side effects.

A safer architecture is:

```text
LLM intent
    ↓
Tool call
    ↓
Validation
    ↓
Authorization
    ↓
Tool execution
    ↓
Observation
    ↓
LLM
```

`v0.6` adds that authorization boundary.

And that small architectural change has a big implication:

> **The LLM decides what it wants to do. The harness decides what it is allowed to do.**

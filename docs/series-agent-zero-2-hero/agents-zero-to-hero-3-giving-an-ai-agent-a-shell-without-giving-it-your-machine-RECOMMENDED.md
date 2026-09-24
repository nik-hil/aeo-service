# Agents Zero to Hero #3: Giving an AI Agent a Shell Without Giving It Your Machine

## Agents Zero to Hero #3: Giving an AI Agent a Shell Without Giving It Your Machine

Our AI agent can now inspect and modify files.

That happened in `v0.2-new-tools`, where we introduced:

```text
list_files
read_file
write_file
```

We also introduced an important boundary:

```text
agent_workspace
```

All filesystem operations are restricted to that workspace.

But a real coding agent still needs another major capability:

```text
shell commands
```

A developer doesn't interact with a repository only through file reads and writes.

We use commands such as:

```bash
git status
git diff
pytest
python -m ...
grep
ls -la
pip list
```

So our next step is obvious:

> Give the agent a shell.

Unfortunately, a naive implementation would be something like:

```python
subprocess.run(command, shell=True)
```

and that is exactly what we do **not** want.

This article is about adding a shell tool while introducing the first meaningful execution boundaries in the harness.

Repository:

https://github.com/nik-hil/agents-zero-2-hero

Tag:

```text
v0.3-bash-tut
```

* * *

# Why shell access is different

Consider our previous tools.

`read_file` accepts:

```text
filepath
```

`write_file` accepts:

```text
filepath + content
```

Their behavior is relatively constrained.

A shell command is fundamentally different.

This:

```bash
ls
```

is harmless.

This:

```bash
pytest
```

is useful.

But these could be dangerous:

```bash
rm -rf /
curl ... | sh
chmod ...
```

and potentially destructive even without malicious intent:

```bash
git reset --hard
```

So we need a policy.

The first policy in this project is intentionally simple:

> **Allow a small, explicit set of commands.**

* * *

# The bash tool

The new function is:

```python
def bash(command: str, verbose: bool = True) -> Dict:
```

The implementation describes itself as a constrained command runner.

It deliberately does **not** execute commands through a shell.

That distinction is critical.

* * *

# Why `shell=False`?

The actual subprocess call is:

```python
result = subprocess.run(
    args,
    cwd=WORKSPACE,
    capture_output=True,
    text=True,
    timeout=20,
    shell=False,
    env={
        "PATH": "/usr/bin:/bin",
        "HOME": WORKSPACE,
    },
)
```

The important property is:

```python
shell=False
```

We do not want to hand a raw string to a shell interpreter.

Instead, we first parse the command into arguments.

For example:

```text
"grep -r TODO ."
```

becomes roughly:

```python
[
    "grep",
    "-r",
    "TODO",
    "."
]
```

and `subprocess.run()` receives the argument list directly.

This removes an entire class of shell interpretation behavior.

* * *

# Parsing the command

The tool uses:

```python
args = shlex.split(command)
```

instead of:

```python
command.split(" ")
```

That distinction matters because shell-style quoting exists.

For example:

```bash
echo "hello world"
```

should be interpreted as something like:

```python
[
    "echo",
    "hello world"
]
```

`shlex.split()` gives us shell-like tokenization without actually invoking a shell.

* * *

# The allowlist

The next boundary is the most visible one.

The tool defines:

```python
ALLOWED_COMMANDS = {
    "ls",
    "grep",
    "pip list",
    "pwd",
    "cat",
    "echo",
    "python",
    "python3",
    "pip",
}
```

The exact implementation is intentionally small and educational.

The agent can only execute commands that appear in this policy.

This means the control flow becomes:

```text
LLM generates command
        ↓
parse command
        ↓
check allowlist
        ↓
allowed? ───── no ────► reject
        │
       yes
        ↓
execute
```

That is an important shift.

The model is no longer directly in charge of execution.

It is requesting execution from a policy-controlled component.

* * *

# Invalid commands become observations

Suppose the model requests:

```bash
rm -rf temp
```

The tool does not execute it.

Instead it returns:

```python
{
    "error": "Command not allowed",
    "allowed_commands": sorted(ALLOWED_COMMANDS),
    "attempted": cmd,
}
```

This is another recurring pattern in agent harness design:

```text
unsafe action
    ↓
policy rejection
    ↓
structured result
    ↓
model can recover
```

The harness enforces the policy.

The LLM receives the consequence.

* * *

# Path traversal protection for commands

There is another important check:

```python
for a in args[1:]:
    if a.startswith("/") or ".." in a:
        return {
            "error":
                "Absolute paths and parent directory access are not allowed",
            "argument": a,
        }
```

So this is rejected:

```bash
cat ../../secret.txt
```

and so is:

```bash
cat /etc/passwd
```

This is an important concept:

> Restricting the executable name is not enough.

You also need to consider the arguments.

A command can be harmless by name but dangerous through its parameters.

* * *

# Working directory isolation

The subprocess runs with:

```python
cwd=WORKSPACE
```

This reinforces the earlier workspace boundary.

Conceptually:

```text
Host machine
│
├── application
├── secrets
├── user files
│
└── agent_workspace
       │
       ├── project files
       ├── generated files
       └── agent commands
```

The agent operates from the workspace, but `cwd=WORKSPACE` alone is not a guarantee that commands cannot access files outside it. The separate argument checks reject absolute paths and arguments containing `..`; those checks, rather than the working-directory setting, reject the `cat` examples above.

These controls are layers, not a complete sandbox.

* * *
# Environment isolation

The subprocess environment is also restricted:

```python
env = {
    "PATH": "/usr/bin:/bin",
    "HOME": WORKSPACE,
}
```

This is another important pattern.

The environment itself can influence command execution.

By controlling it, we reduce accidental access to host-specific state.

Again, this is not a perfect sandbox.

It is another layer.

And that is how real agent security tends to work:

```text
policy
+
filesystem boundary
+
process boundary
+
container boundary
+
resource limits
```

rather than relying on one magic protection.

* * *

# Why Docker enters the picture

At `v0.3`, the repository also introduces Docker.

The `Dockerfile` starts from:

```dockerfile
FROM python:3.14-slim
```

and creates a non-root user:

```dockerfile
RUN useradd -m agent
```

The container then switches to:

```dockerfile
USER agent
```

This gives us a basic containerized execution environment.

* * *

# Why run the agent as non-root?

This is one of those security principles that becomes especially important when software is AI-controlled.

The agent should not need:

```text
root
```

to do normal coding-agent work.

Running as an unprivileged user reduces the impact of a tool escaping the expected execution path.

Again:

```text
LLM
```

is not trusted enough to justify unnecessary privileges.

* * *

# Docker Compose adds another layer

The Compose configuration adds:

```yaml
security_opt:
  - no-new-privileges:true

cap_drop:
  - ALL

pids_limit: 64

mem_limit: 512m
```

The container also uses:

```yaml
tmpfs:
  - /tmp
```

and mounts the project/workspace.

Now our architecture looks more like:

```text
                   ┌───────────────┐
                   │      LLM      │
                   └───────┬───────┘
                           │
                      tool call
                           │
                   ┌───────▼───────┐
                   │    Harness    │
                   │               │
                   │ permissions   │
                   │ validation    │
                   │ workspace     │
                   └───────┬───────┘
                           │
                    subprocess
                           │
                   ┌───────▼───────┐
                   │    Docker     │
                   │   container   │
                   └───────────────┘
```

We have now separated the model, harness, and execution environment.

* * *

# The tool returns structured execution data

A command that runs returns structured execution data, whether it succeeds or fails:

```python
{
    "command": args,
    "stdout": ...,
    "stderr": ...,
    "exit_code": result.returncode,
    "success": result.returncode == 0,
}
```

This is important.

The agent doesn't only need:

```text
stdout
```

It needs structured execution state.

For example:

```text
exit_code = 1
success = false
stderr = ...
```

tells the model:

> The operation failed.

That means the model can potentially change strategy.

* * *
# The difference between an assistant and an agent

This checkpoint makes the distinction much clearer.

A traditional assistant might answer:

```text
Run pytest.
```

An agent can actually do:

```text
bash("pytest")
```

observe:

```text
exit_code = 1
stderr = ...
```

then reason:

```text
The test failed.
Let's inspect the relevant file.
```

then:

```text
read_file(...)
```

then:

```text
edit_file(...)
```

and eventually:

```text
bash("pytest")
```

again.

That is an agentic workflow.

* * *

# The interesting part is not the shell tool

The actual `bash()` function is not the most important lesson.

The interesting lesson is the idea of **capability mediation**.

The model says:

```text
I want to run X.
```

The harness says:

```text
Let me check whether X is allowed.
```

Only then:

```text
execute X
```

This pattern will become the foundation of permissions later.

In other words:

> The model requests capabilities; the harness grants or denies them.

That is a much more robust architecture than:

> The model can execute anything it wants.

* * *

# Why not just trust the prompt?

Someone might ask:

> If the system prompt says “never use dangerous commands”, isn't that enough?

No.

Prompt instructions are behavioral guidance.

They are not enforcement.

A robust system must distinguish between:

```text
policy instruction
```

and:

```text
policy enforcement
```

The latter should live in code.

For example:

```python
if cmd not in ALLOWED_COMMANDS:
    return error
```

The model cannot override that by generating different text.

That is exactly the kind of separation we want in an agent harness.

* * *

# The limits of this approach

This implementation is intentionally educational.

An allowlist is useful, but it is not a complete security model.

For example:

```text
allowed command
```

does not automatically mean:

```text
safe execution
```

Argument handling matters.

The environment matters.

The filesystem matters.

The user permissions matter.

The container matters.

Resource limits matter.

This is why the roadmap eventually introduces a dedicated permission layer.

* * *

# One subtle implementation problem

The code is intentionally simple enough that you can inspect all of it.

That is one of the main goals of the project.

The lesson is not:

> Copy this shell wrapper into production.

The lesson is:

> Understand where the security boundary lives.

A production-grade agent execution layer might additionally include:

```text
command policy
argument policy
filesystem policy
network policy
resource quotas
timeouts
process isolation
audit logging
approval flows
```

The shell wrapper is simply the beginning.

* * *

# Running v0.3

Checkout:

```bash
git checkout v0.3-bash-tut
```

Then:

```bash
docker compose up --build
```

The repository's lesson configuration also identifies this checkpoint as:

```text
bash (allowlisted) + Docker
```

with Docker Compose as its normal execution path.

* * *

# What has our agent become?

Let's compare the first three checkpoints.

### v0.1

```text
LLM
 ├── execute_code
 └── finish
```

### v0.2

```text
LLM
 ├── execute_code
 ├── list_files
 ├── read_file
 ├── write_file
 └── finish

        ↓

agent_workspace
```

### v0.3

```text
LLM
 │
 ▼
Harness
 │
 ├── file tools
 ├── Python execution
 ├── guarded bash
 └── finish
 │
 ▼
containerized environment
```

The architecture is starting to look like an actual coding-agent harness.

* * *

# But something is still missing

Imagine the agent wants to modify a 500-line Python file.

With our current primitives, it can use:

```text
write_file
```

and replace the whole file.

That's a terrible editing primitive.

The model has to regenerate everything.

That creates risks:

```text
lost changes
unrelated edits
larger token usage
higher chance of corruption
harder review
```

A coding agent needs something much closer to what a developer actually does:

```text
find this code
replace that code
```

It also needs fast code search.

That leads directly to `v0.4`.

* * *

## Next checkpoint

In the next article we'll introduce:

```text
edit_file
code_search
```

This is where the harness begins to look less like a chatbot with tools and more like a real coding environment.

* * *

## Repository

https://github.com/nik-hil/agents-zero-2-hero

Tag:

```text
v0.3-bash-tut
```

# Agents Zero to Hero #13: Building a Verification Loop for AI Agents

## Agents Zero to Hero #13: Building a Verification Loop for AI Agents

**Git tag:** `v0.13-verify-loop` **Pillar:** 🔄 Agent Loop **Series:** Agents Zero to Hero — Building an AI Coding Agent from First Principles

An AI coding agent that can write code is useful.

An AI coding agent that can **check whether its code actually works** is much more interesting.

That is the idea behind `v0.13-verify-loop` in my [Agents Zero 2 Hero](https://github.com/nik-hil/agents-zero-2-hero) project.

In the previous lessons, the agent gradually learned how to:

*   use tools
    
*   read and write files
    
*   execute guarded shell commands
    
*   perform precise code edits
    
*   work with multiple LLM providers
    
*   enforce permissions
    
*   run lifecycle hooks
    
*   maintain persistent memory
    
*   compact long contexts
    
*   load skills on demand
    
*   connect to MCP servers
    
*   delegate work to subagents
    

But there was still a fundamental gap.

The agent could **change the code**, but it could not systematically **prove to itself that the change worked**.

This lesson closes that loop.

* * *

## What is an AI agent verification loop?

A basic coding agent often looks like this:

```text
User request
     ↓
LLM
     ↓
Tool call
     ↓
Edit code
     ↓
Finish
```

The problem is obvious:

> How does the agent know that the code it generated actually works?

The verification loop changes the architecture to:

```text
User request
     ↓
LLM
     ↓
run_tests
     ↓
Read failure
     ↓
Edit code
     ↓
run_tests
     ↓
Read result
     ↓
   ┌───────────────┐
   │ Tests failing │
   └───────┬───────┘
           │
           ↓
        Fix code
           │
           └───────────────┐
                           ↓
                       run_tests
                           │
                           ↓
                    Tests passing
                           │
                           ↓
                         finish
```

The important change is that **test execution becomes an agent tool**.

The model doesn't need a special hard-coded "fix bug" algorithm.

It gets feedback as data and decides what to do next.

* * *

## What does `v0.13-verify-loop` add?

The tag introduces one main capability:

```text
run_tests
```

The tool runs the test suite and returns structured information:

```python
{
    "passed": True,
    "returncode": 0,
    "output": "..."
}
```

or, when something fails:

```python
{
    "passed": False,
    "returncode": 1,
    "output": "FAIL: ..."
}
```

This is deliberately simple.

The verifier doesn't try to understand the code.

It doesn't ask an LLM why the test failed.

It doesn't automatically modify anything.

It simply executes the tests and returns the result.

The **agent remains responsible for interpreting the result and deciding what to do next**.

That separation is important.

* * *

# How does the `run_tests` tool work?

The implementation lives in `verify.py`.

At its core:

```python
def run_tests(workspace, command=None, timeout=60):
    workspace = Path(workspace)

    cmd = command or [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        ".",
        "-p",
        "test_*.py",
    ]

    ...
```

The default test runner uses Python's standard-library `unittest` discovery.

That means this lesson doesn't introduce another testing dependency.

The agent can simply run:

```bash
python -m unittest discover
```

through the verification layer.

* * *

## Why return test results as data?

One of the most important design decisions is that `run_tests()` doesn't just print output.

It returns a structured dictionary:

```python
return {
    "passed": r.returncode == 0,
    "returncode": r.returncode,
    "output": output[-2000:] if output else "(no output)",
}
```

These fields describe a completed test process. If the test run times out, the verifier instead returns `passed=False` and an `error` message, without `returncode` or `output`. That distinguishes a timeout from a completed run whose output the agent can inspect.

This makes the result part of the agent's context.

The LLM can now reason over:

```text
passed = false

FAIL: test_add
Expected: 5
Actual:  -1
```

and decide:

> The implementation of `add()` is probably incorrect. I should inspect and fix it.

This illustrates a broader agent architecture principle:

> **Tools should return machine-readable observations that the model can use for its next action.**

The verifier produces an observation.

The agent decides the next action.

* * *
# Why limit the test output?

A test suite can generate a huge amount of output.

Imagine a repository with thousands of tests.

Returning all test output to the LLM could consume a significant portion of the context window.

So `verify.py` keeps only the tail:

```python
output = (r.stdout + r.stderr).strip()

return {
    "passed": r.returncode == 0,
    "returncode": r.returncode,
    "output": output[-2000:] if output else "(no output)",
}
```

This is a small implementation detail with an important consequence.

The verification tool is also participating in **context management**.

The architecture now has several layers controlling context:

```text
Tests
  ↓
Verification tool
  ↓
Small structured result
  ↓
Agent context
  ↓
LLM
```

That complements the context compaction work from `v0.9`.

Compaction controls accumulated conversation history.

The verification tool controls how much test output enters that history in the first place.

* * *

# How does the agent know it should keep fixing?

The other half of the implementation is in the system prompt.

The agent is explicitly instructed:

```text
If the task involves code that has tests, run_tests to verify;
if they fail, read the output, fix the code, and run_tests again —
repeat until they pass before you finish.
```

This is an important distinction.

There is no complicated state machine such as:

```python
if tests_failed:
    fix()
```

inside the harness.

Instead, the harness gives the model:

1.  a test tool
    
2.  a rule describing the expected behavior
    
3.  the existing file-editing tools
    

The LLM performs the reasoning loop.

Conceptually:

```text
LLM
 │
 ├── run_tests()
 │
 │   └── FAILED
 │
 ├── read_file()
 │
 ├── edit_file()
 │
 ├── run_tests()
 │
 │   └── PASSED
 │
 └── finish()
```

This is much closer to the general-purpose agent architecture we're building throughout this series.

* * *

# The `v0.13` demo

The demo deliberately creates broken code.

When:

```bash
AGENT_VERIFY=1 python coding_agent.py
```

runs, the harness creates:

```python
def add(a, b):
    return a - b
```

and a test expecting:

```python
self.assertEqual(add(2, 3), 5)
```

So the initial state is intentionally broken.

The agent receives the task:

```text
The tests in this workspace are failing.
Run them, read the failure, fix the bug in calc.py,
and run the tests again until they pass.
Then finish.
```

The expected sequence is:

```text
run_tests
    ↓
FAIL
    ↓
read failure
    ↓
inspect calc.py
    ↓
edit calc.py
    ↓
run_tests
    ↓
PASS
    ↓
finish
```

The agent has now become an **iterative coding system** instead of a one-shot code generator.

* * *

# What does the complete agent loop look like now?

At `v0.13`, the conceptual loop has become significantly richer.

Simplified:

```python
for iteration in range(max_iterations):

    messages, compacted = compactor.maybe_compact(messages)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=schemas,
        tool_choice="auto",
    )

    message = response.choices[0].message

    if message.tool_calls:
        for tool_call in message.tool_calls:

            tool_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)

            # Permission layer
            decision = permissions.check(tool_name, args)

            # Pre-tool hooks
            allowed, reason, args = hooks.run_pre(
                tool_name,
                args,
            )

            # Execute
            result = tools_map[tool_name](**args)

            # Post-tool hooks
            result = hooks.run_post(
                tool_name,
                args,
                result,
            )

            # Feed observation back to model
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })
```

The interesting thing is that `run_tests` fits into this architecture without requiring a new agent-loop abstraction.

It is just another tool.

That is a strong sign that the architecture is holding together.

* * *

# Why is verification a tool instead of special agent logic?

This is one of the most important architectural questions in this lesson.

We could have written:

```python
if task_is_coding:
    automatically_run_tests()
```

But that couples the agent loop to a particular workflow.

Instead:

```text
Agent loop
    │
    ├── read_file
    ├── write_file
    ├── edit_file
    ├── bash
    ├── run_tests
    ├── spawn_subagent
    ├── MCP tools
    └── finish
```

The loop doesn't need to know what `run_tests` means.

It only knows:

```text
schema → tool call → result → next model turn
```

This is the same architectural pattern used throughout the series.

The agent loop is generic.

Capabilities are implemented as tools.

* * *

# A subtle problem: stale Python bytecode

This lesson exposed a surprisingly interesting bug.

Suppose the agent runs:

```text
run_tests()
```

and gets:

```text
FAIL
```

It edits the Python file.

Then it immediately runs:

```text
run_tests()
```

again.

You might expect the test runner to execute the new source code.

But Python has a bytecode cache:

```text
__pycache__/
    calc.cpython-*.pyc
```

Under certain circumstances, CPython can consider the cached bytecode valid based on source metadata such as file size and modification time.

A very fast edit that keeps the same file size can create a particularly nasty situation:

```text
old source
   ↓
old bytecode

edit source
   ↓
same size + same timestamp granularity
   ↓
Python may reuse cached bytecode
```

The agent could fix the bug correctly and still receive the old failure.

From the agent's perspective, this is disastrous.

It might conclude:

> My fix didn't work.

And then modify correct code again.

* * *

# How does `run_tests` prevent stale results?

The verifier clears Python bytecode caches before running tests:

```python
for pc in workspace.rglob("__pycache__"):
    shutil.rmtree(pc, ignore_errors=True)
```

It also sets:

```python
PYTHONDONTWRITEBYTECODE=1
```

through the test environment:

```python
env = {
    **os.environ,
    "PYTHONDONTWRITEBYTECODE": "1",
}
```

This gives the verification loop a much stronger property:

> The result should reflect the current source state rather than stale cached bytecode.

This is a great example of why agent infrastructure has to care about its execution environment.

The LLM may be the reasoning component, but the harness controls the reality that the LLM observes.

* * *

# What happens if the test suite hangs?

The verifier also has a timeout:

```python
def run_tests(workspace, command=None, timeout=60):
```

and:

```python
try:
    r = subprocess.run(
        ...,
        timeout=timeout,
    )
except subprocess.TimeoutExpired:
    return {
        "passed": False,
        "error": f"tests timed out after {timeout}s",
    }
```

This is important because an autonomous agent cannot safely assume that arbitrary code will always terminate.

Without a timeout:

```text
agent
  ↓
run_tests
  ↓
test hangs
  ↓
agent waits forever
```

With a timeout:

```text
agent
  ↓
run_tests
  ↓
timeout
  ↓
structured failure
  ↓
agent can reason about next action
```

The verifier therefore acts as a controlled execution boundary.

* * *

# How is the tool exposed to the LLM?

Inside `coding_agent.py`:

```python
def run_tests(path: str = ".") -> dict:
    """Run the test suite in the workspace and report pass/fail + output."""
    target = (WORKSPACE / path).resolve()

    if not target.is_relative_to(WORKSPACE):
        return {"error": "path must be inside the workspace"}

    cmd = [
        _sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(target),
        "-p",
        "test_*.py",
    ]

    return verify.run_tests(WORKSPACE, command=cmd)
```

There are two useful details here.

### 1\. The agent can specify a path

The tool supports:

```text
run_tests(".")
```

or a narrower workspace location.

### 2\. Workspace boundaries are enforced

The path must remain inside:

```python
WORKSPACE
```

The verifier isn't allowed to escape the agent's workspace through a crafted path.

This continues the security model introduced in earlier lessons.

* * *

# What tests were added for the verifier?

The lesson includes offline tests in:

```text
tests/test_verify.py
```

There are three particularly useful cases.

## 1\. Failing suite

The test writes:

```python
def add(a, b):
    return a - b
```

and verifies that:

```python
result["passed"]
```

is false.

* * *

## 2\. Passing suite

It then uses:

```python
def add(a, b):
    return a + b
```

and verifies:

```python
result["passed"] is True
```

* * *

## 3\. Fix after failure

The most interesting test is:

```python
(self.dir / "calc.py").write_text(BUGGY)

self.assertFalse(
    verify.run_tests(self.dir)["passed"]
)

(self.dir / "calc.py").write_text(FIXED)

self.assertTrue(
    verify.run_tests(self.dir)["passed"]
)
```

This directly tests the stale-bytecode scenario.

The important property isn't simply:

```text
bad code → fail
```

or:

```text
good code → pass
```

It's:

```text
bad code
   ↓
FAIL
   ↓
modify code
   ↓
PASS
```

That's the exact state transition required by an agent verification loop.

* * *

# Verification changes the meaning of "done"

Before this lesson, an agent could effectively decide:

```text
"I generated the requested code."
```

and finish.

After this lesson, the intended workflow is:

```text
"I generated the code."

        ↓

"Does it work?"

        ↓

"No."

        ↓

"Why?"

        ↓

"Fix it."

        ↓

"Does it work now?"

        ↓

"Yes."

        ↓

"Now I'm done."
```

This distinction is fundamental.

A coding agent shouldn't treat **generation** as the definition of completion.

It should treat **verified behavior** as a stronger completion signal.

* * *

# Verification loop vs context compaction

This lesson also connects directly to `v0.9`.

They solve different problems.

### Context compaction

Compaction asks:

> How do I keep one long agent conversation within the model's context budget?

```text
long conversation
       ↓
summarize old history
       ↓
smaller context
```

### Verification loop

Verification asks:

> How do I make the agent improve its output based on external feedback?

```text
code
 ↓
test
 ↓
failure
 ↓
fix
 ↓
test
```

So:

```text
Compaction = context management

Verification = feedback management
```

A serious coding agent needs both.

* * *

# Verification loop vs subagents

`v0.12` introduced subagents.

A subagent answers:

> Who should perform this work?

For example:

```text
Parent agent
    ↓
spawn_subagent
    ↓
Child agent
    ↓
implement feature
```

The verification loop answers:

> How do we know the work is correct?

```text
Agent
  ↓
implement
  ↓
run_tests
  ↓
fix
  ↓
run_tests
```

These capabilities can be combined:

```text
Parent
  │
  ├── spawn_subagent
  │       ↓
  │    implement
  │       ↓
  │    run_tests
  │       ↓
  │    fix
  │       ↓
  │    return
  │
  └── verify final result
```

That is where the architecture starts becoming substantially more interesting than a simple tool-calling loop.

* * *

# The complete architecture at v0.13

The journey from `v0.1` to `v0.13` now looks like this:

```text
                         ┌───────────────────────┐
                         │         LLM           │
                         │   reasoning / plan    │
                         └───────────┬───────────┘
                                     │
                              tool calls
                                     │
                         ┌───────────▼───────────┐
                         │      Agent Loop        │
                         │                        │
                         │  context / iteration   │
                         │  tool dispatch         │
                         │  finish                │
                         └───────────┬───────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
     ┌──────────┐              ┌───────────┐              ┌───────────┐
     │ Toolkit  │              │ Governance│              │  Context  │
     │          │              │           │              │           │
     │ files    │              │ permissions│              │ memory    │
     │ bash     │              │ hooks      │              │ sessions  │
     │ edit     │              │            │              │ compaction│
     │ MCP      │              └───────────┘              │ skills    │
     └──────────┘                                         └───────────┘
          │
          │
          ▼
     ┌───────────┐
     │   Swarm   │
     │           │
     │ subagents │
     └─────┬─────┘
           │
           ▼
     ┌───────────────┐
     │ Verification  │
     │               │
     │ run_tests     │
     │     ↓         │
     │ observe       │
     │     ↓         │
     │ fix           │
     │     ↓         │
     │ rerun         │
     └───────────────┘
```

The architecture is still based on a surprisingly small primitive:

```text
LLM
 ↓
tool call
 ↓
tool result
 ↓
LLM
```

Everything else is infrastructure around that primitive.

* * *

# What are the limitations of this verification loop?

This implementation is intentionally educational, not a production test-execution service.

There are several limitations.

## 1\. It assumes Python `unittest`

The verifier currently defaults to:

```bash
python -m unittest discover
```

A production system would likely need adapters for:

```text
pytest
npm test
go test
cargo test
mvn test
gradle test
```

and potentially project-specific commands.

* * *

## 2\. Test output is truncated

Only the last 2,000 characters are returned.

That's useful for context control but can hide the beginning of a failure.

A more sophisticated implementation could return:

```json
{
  "passed": false,
  "failed_tests": [...],
  "summary": "...",
  "output_tail": "...",
  "output_path": "..."
}
```

* * *

## 3\. Passing tests don't prove correctness

This is perhaps the most important limitation.

```text
tests pass
```

does not mean:

```text
software is correct
```

It only means the implementation passed the available test suite.

An agent can therefore still produce incorrect behavior when tests are incomplete.

* * *

## 4\. The agent can get stuck

A poorly designed agent could do:

```text
run_tests
FAIL

edit

run_tests
FAIL

edit

run_tests
FAIL

...
```

The harness already has:

```python
max_iterations=15
```

which bounds iterations of the overall agent loop, not a dedicated count of repair attempts. This complements the verifier's default 60-second timeout: the timeout bounds an individual test run, while `max_iterations` bounds continued agent iterations even when fixes never produce passing tests.

A more advanced verification system could track:

*   repeated failures
    
*   unchanged failures
    
*   oscillating patches
    
*   test progress
    
*   maximum repair attempts
    
*   cost budgets
    

* * *
# What would a production verification loop need?

The educational implementation gives us the core abstraction:

```text
verification = execute + observe
```

A production implementation could evolve this into:

```text
             ┌───────────────┐
             │   Implement   │
             └───────┬───────┘
                     ↓
             ┌───────────────┐
             │    Verify     │
             └───────┬───────┘
                     ↓
               ┌───────────┐
               │   Pass?   │
               └─────┬─────┘
                  yes│  no
                     │
          ┌──────────┘
          ↓
       finish

          no
          ↓
    ┌───────────────┐
    │ Diagnose      │
    │ failure       │
    └───────┬───────┘
            ↓
    ┌───────────────┐
    │ Repair        │
    └───────┬───────┘
            │
            └──────────→ Verify
```

And eventually verification could include more than tests:

```text
unit tests
integration tests
type checking
linting
security scanning
build
API contract checks
static analysis
browser tests
performance checks
```

The important architectural idea remains the same:

> **External feedback becomes another observation available to the agent.**

* * *

# Why this is an important milestone

`v0.13` is the final planned lesson in this version of the curriculum.

The progression is now:

```text
v0.1  Agent loop
v0.2  Files
v0.3  Shell
v0.4  Precise editing
v0.5  Multiple providers
v0.6  Permissions
v0.7  Hooks
v0.8  Memory
v0.9  Compaction
v0.10 Skills
v0.11 MCP
v0.12 Subagents
v0.13 Verification
```

The important thing isn't the number of features.

It's how each feature adds one missing part of an agent harness.

At the beginning:

```python
while True:
    ask_llm()
```

At the end:

```text
                    ┌─────────────┐
                    │     LLM     │
                    └──────┬──────┘
                           │
                     decide action
                           │
                    ┌──────▼──────┐
                    │ Agent Loop  │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
     Tools             Governance          Context
        │                  │                  │
     Files              Permissions         Memory
     Bash               Hooks              Sessions
     MCP                                   Compaction
     Edit                                  Skills
        │
        ▼
    Subagents
        │
        ▼
   Verification
        │
        ▼
   Feedback → Fix → Verify
```

The agent is no longer merely producing an answer.

It has the beginnings of an **engineering feedback system**.

* * *

# Final takeaway

The most important idea from `v0.13` is simple:

> **An AI coding agent becomes significantly more useful when it can observe the consequences of its own actions.**

Without verification:

```text
generate → hope
```

With verification:

```text
generate → test → observe → fix → test → verify
```

And that is the fundamental transition from an LLM-powered code generator to an iterative coding agent.

The `v0.13-verify-loop` implementation is intentionally small, but the abstraction is powerful:

```python
result = run_tests(...)
```

becomes an observation that the model can reason about.

The harness provides the capability.

The model provides the diagnosis and decision-making.

The environment provides the feedback.

And the loop continues until the result satisfies the verification criteria—or the agent reaches its execution boundary.

That is the verification loop.

* * *

## Series recap

This is **Agents Zero to Hero #13**.

The complete journey:

1.  **v0.1** — Build the minimal agent loop
    
2.  **v0.2** — Give it filesystem tools
    
3.  **v0.3** — Add guarded shell execution
    
4.  **v0.4** — Add precise editing and search
    
5.  **v0.5** — Support multiple LLM providers
    
6.  **v0.6** — Add permission governance
    
7.  **v0.7** — Add lifecycle hooks
    
8.  **v0.8** — Add persistent memory
    
9.  **v0.9** — Add context compaction
    
10.  **v0.10** — Add on-demand skills
     
11.  **v0.11** — Add MCP
     
12.  **v0.12** — Add context-isolated subagents
     
13.  **v0.13** — Close the loop with verification
     

From a bare `while` loop to a small, understandable AI coding-agent harness—built one capability at a time.

# Agents Zero to Hero #1: Building an AI Agent from Scratch with Tool Calling

Building an AI agent sounds deceptively simple.

Call an LLM. Give it a prompt. Get an answer.

But that is not really an agent.

An LLM becomes an agent when it can **decide to take actions**, invoke capabilities outside the model, observe the result, and continue working until the task is complete.

That sounds complicated when described using terms like *agentic workflows*, *tool calling*, *harnesses*, and *autonomous coding agents*.

So instead of starting with a framework, I decided to build one myself.

This repository is my attempt to understand the mechanics of an AI agent harness **from first principles**, one Git tag at a time.

Repository:

https://github.com/nik-hil/agents-zero-2-hero

This series starts at the smallest useful building block.

Our first milestone is:

> **An LLM that can call a Python tool and decide when it is finished.**

* * *

## What exactly are we building?

The project is called **Agents Zero 2 Hero**.

The idea is deliberately incremental:

```text
v0.1 → basic tool calling
v0.2 → filesystem tools
v0.3 → shell execution
v0.4 → precise editing and code search
v0.5 → provider abstraction
...
```

Eventually, the harness is intended to grow toward capabilities such as permissions, hooks, memory, context compaction, skills, MCP, subagents, and verification loops.

But all of that starts with one simple loop.

The repository defines the idea roughly like this:

```text
harness = tools + knowledge + observation + action + permissions
```

The LLM supplies the intelligence.

The harness provides the mechanism through which that intelligence can interact with the outside world.

* * *

# The agent loop

The most important concept in the entire project is the agent loop.

To build this basic Python agent without an agent framework, define Python tools and their schemas, send the schemas and conversation to the model, dispatch requested calls through a tool registry, and add the results to the conversation. Repeat so the model can observe each result and decide whether to act again or finish.

At a high level, the loop looks like this in simplified pseudocode. This sketch stops when there are no tool calls; the explicit `finish` signal is covered below.

```python
while True:
    response = client.chat.completions.create(
        messages=messages,
        tools=TOOL_SCHEMAS,
    )

    if not response.tool_calls:
        break

    for call in response.tool_calls:
        result = TOOLS[call.name](**call.args)
        messages.append(tool_result(call, result))
```

Conceptually:

```text
User
  │
  ▼
┌───────────┐
│    LLM    │
└─────┬─────┘
      │
      │ decides what to do
      ▼
┌───────────┐
│   Tool    │
└─────┬─────┘
      │
      │ result
      ▼
┌───────────┐
│    LLM    │
└─────┬─────┘
      │
      ├──── another tool?
      │
      └──── finish?
```

The key distinction is:

> **The model decides what should happen. The harness controls how it happens.**

That distinction becomes extremely important as an agent becomes more capable.

* * *

# Our first two tools

At `v0.1-basic-tool`, the harness exposes exactly two tools:

```text
execute_code
finish
```

The first lets the model perform computation.

The second lets the model explicitly terminate the task.

The tool map is:

```python
TOOLS = {
    "execute_code": execute_code,
    "finish": finish,
}
```

The interesting part is that the LLM does not magically know how these Python functions work.

We explicitly describe them using tool schemas.

* * *

# Tool schemas

The `execute_code` function schema declares one required input: a string named `code`. We pass tool definitions with `tools=TOOL_SCHEMAS` and let the model decide whether to request a tool with `tool_choice="auto"`, as shown in the model call below. The schema describes the interface; it does not execute Python.

```python
{
    "type": "function",
    "function": {
        "name": "execute_code",
        "description": "Execute Python code and return stdout or error.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Python code to execute"
                }
            },
            "required": ["code"],
            "additionalProperties": False
        }
    }
}
```

This schema is effectively the contract between the model and the harness.

The model sees:

```text
Tool name: execute_code

Input:
{
    "code": "..."
}
```

and can decide:

> I need to execute some Python.

The harness then translates that model decision into an actual function invocation.

* * *

# Implementing execute\_code

The implementation is intentionally small. It writes the supplied Python to `temp.py`, then runs it with `subprocess.run`, capturing stdout and stderr as text with a ten-second timeout. A successful exit returns stdout in `output`; a nonzero exit returns stderr in `error`. Exceptions, including a timeout, return their text in `error`.

```python
def execute_code(code: str):
    try:
        with open("temp.py", "w") as f:
            f.write(code)

        result = subprocess.run(
            ["python", "temp.py"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        os.remove("temp.py")

        if result.returncode == 0:
            return {
                "output": result.stdout.strip(),
                "error": None,
            }

        return {
            "output": None,
            "error": result.stderr.strip(),
        }

    except Exception as e:
        return {
            "output": None,
            "error": str(e),
        }
```

There are already several interesting harness concepts hiding inside this tiny function.

### The model does not execute code directly

The LLM produces structured arguments.

The harness executes the actual function.

That separation creates a control point where we can later add:

*   permissions
    
*   sandboxing
    
*   logging
    
*   timeouts
    
*   validation
    
*   metrics
    
*   policy checks
    

That is why the harness matters.

* * *

# The finish tool

The second tool is even simpler:

```python
def finish(answer: str):
    return {
        "final_answer": answer
    }
```

Why make finishing a tool instead of simply accepting a normal assistant response?

Because it gives the harness an explicit completion signal, with the answer in `final_answer`, rather than relying on a response without tool calls as the stopping rule.

The model can say:

```text
I am done.
```

by calling:

```text
finish(...)
```

The harness then knows it can terminate the loop. The function itself only returns the answer; stopping is the harness's responsibility. The introductory pseudocode omits this explicit finish handling to focus on the tool-result loop.

This becomes very useful as the agent starts performing multi-step work.

* * *

# Running the agent

The main function looks like this:

```python
def run_agent(
    task: str,
    max_iterations: int = 8,
    model="openai/gpt-oss-120b"
):
```

It starts the conversation with a system message:

```text
You are a coding agent.

Rules:
- Use tools when needed.
- When the task is fully complete, call the finish tool exactly once.
- Do not continue reasoning after calling finish.
```

Then:

```python
messages = [
    {
        "role": "system",
        "content": ...
    },
    {
        "role": "user",
        "content": task
    },
]
```

* * *

# Calling the model

Every iteration sends the current conversation and tool definitions:

```python
response = client.chat.completions.create(
    model=model,
    messages=messages,
    tools=TOOL_SCHEMAS,
    tool_choice="auto",
    temperature=0.3,
    max_tokens=2048,
)
```

The important part here is:

```python
tools=TOOL_SCHEMAS
```

We are telling the model:

> These are the actions available to you.

And:

```python
tool_choice="auto"
```

lets the model decide whether it needs a tool.

* * *

# Handling a tool call

To turn a model tool call into a Python function call, parse its JSON arguments and look up its name in `TOOLS`. After execution, return the serialized result in a `tool` message with the matching `tool_call_id`, as shown in the next section.

Suppose the model decides to call:

```text
execute_code
```

The response contains a tool call with JSON arguments.

The harness does:

```python
tool_name = tool_call.function.name
args = json.loads(tool_call.function.arguments)

result = TOOLS[tool_name](**args)
```

This is one of the most important lines in the whole project.

The model gives us:

```text
tool name + arguments
```

The harness performs:

```text
tool name → Python function
```

through the `TOOLS` registry.

* * *

# Feeding the result back to the model

After executing the tool, the harness sends its result back:

```python
messages.append(
    {
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(result),
    }
)
```

Now the model can observe what happened.

For example:

```text
Model:
execute_code(
    code="print(sum(range(1, 16)))"
)

Tool:
{
    "output": "120",
    "error": null
}
```

The model can now reason:

> I have the result. I can provide the answer.

Or perhaps:

> The code failed. I need to try again.

That second possibility is where agent behavior really starts becoming interesting.

* * *

# Why the message history matters

The model does not remember tool executions automatically.

Keep the system instructions and user task in `messages`, then retain the assistant's tool-call message before appending its tool results. Each result's `tool_call_id` links it to the requested call. Send the updated history on the next model request, including any returned error, so the model can decide whether to revise the code and try again.

The harness maintains the conversation state:

```text
system message
      ↓
user task
      ↓
assistant tool call
      ↓
tool result
      ↓
assistant decision
      ↓
tool call
      ↓
tool result
      ↓
...
```

The message history is therefore a critical part of the harness.

Later, this will evolve into a much larger problem:

*   context windows
    
*   memory
    
*   compaction
    
*   session persistence
    
*   project context
    

But the foundation is already present here.

* * *

# The complete flow

Imagine the user asks:

```text
Write and execute a Python function for FizzBuzz up to 15.
Return the output.
```

The agent might perform something like:

```text
USER
  │
  ▼
LLM
  │
  │ execute_code(...)
  ▼
execute_code
  │
  │ stdout
  ▼
LLM
  │
  │ finish(...)
  ▼
finish
  │
  ▼
FINAL ANSWER
```

The important observation is that the LLM is not itself the agent. Agent behavior comes from choosing actions, observing their results, and deciding whether to continue or finish—not merely generating a reply.

The combination is:

```text
LLM + tool definitions + execution engine + state + control loop
```

That is the beginning of the harness.

* * *

# There is already a security problem

It is worth noticing something uncomfortable.

Our tool can execute arbitrary Python code:

```python
subprocess.run(
    ["python", "temp.py"],
    ...
)
```

At this stage there are essentially no meaningful security boundaries. Running the code in a subprocess with a timeout does not make this a sandbox. Permissions, sandboxing, validation, and policy checks belong at the harness's execution control point; this checkpoint does not implement those safeguards.

That is intentional.

This is a learning project.

The goal of the first checkpoint is to make the mechanism visible before introducing additional layers of abstraction and safety.

Later tags will address this.

This is also one of the reasons I prefer building the first version from scratch instead of immediately reaching for a framework.

When a framework gives us:

```python
agent.run(task)
```

we can easily miss what is actually happening underneath.

* * *

# What I learned from v0.1

The first lesson is surprisingly simple:

An agent is not just a prompt.

The minimal architecture is:

```text
             ┌────────────┐
             │     LLM    │
             └─────┬──────┘
                   │
             tool decision
                   │
                   ▼
             ┌────────────┐
             │  Harness   │
             └─────┬──────┘
                   │
                execute
                   │
                   ▼
             ┌────────────┐
             │    Tool    │
             └─────┬──────┘
                   │
                result
                   │
                   └──────────► LLM
```

The harness is responsible for connecting **model decisions** to **real-world actions**.

And that means the harness becomes the natural place for:

```text
security
permissions
observability
state
tool execution
error handling
policy
```

* * *

# Running the project

To run the `v0.1-basic-tool` example, clone the repository, check out that tag, create and activate a virtual environment, install `requirements.txt`, and configure your LLM provider using the repository instructions for that version. Then run `python client.py` followed by `python coding_agent.py`.

Clone the repository:

```bash
git clone https://github.com/nik-hil/agents-zero-2-hero.git
cd agents-zero-2-hero
```

Check out the first lesson:

```bash
git checkout v0.1-basic-tool
```

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure your LLM provider according to the repository instructions.

Then:

```bash
python client.py
python coding_agent.py
```

* * *

# What comes next?

We currently have an agent that can execute Python.

But coding agents need more than computation.

They need to:

```text
see files
read files
create files
modify files
inspect projects
```

That leads directly to the next checkpoint.

## v0.2 — Giving the agent a filesystem

In the next article we'll add three tools:

```text
list_files
read_file
write_file
```

More importantly, we'll introduce a concept that every serious agent harness needs:

> **The agent should operate inside a controlled workspace rather than directly on the entire machine.**

That is where the simple tool-calling loop starts becoming an actual coding-agent harness.

* * *

## Repository

https://github.com/nik-hil/agents-zero-2-hero

Tag:

```text
v0.1-basic-tool
```

The point of this series is not to build another agent framework.

It is to understand what the frameworks are doing for us.

One Git tag at a time.
# Agents Zero to Hero #11: Connecting an AI Agent to External Tools with MCP

# Agents Zero to Hero #11: Connecting an AI Agent to External Tools with MCP

Until now, every tool in my AI coding agent lived inside the agent harness.

If I wanted the agent to use a new capability, I had to write another Python function and add its schema to the harness.

That works.

But it doesn't scale.

Imagine wanting to give the agent access to:

*   GitHub
    
*   a database
    
*   a browser
    
*   Slack
    
*   cloud infrastructure
    
*   monitoring systems
    
*   internal company APIs
    

Do we really want to implement every integration ourselves?

This is the problem that the **Model Context Protocol (MCP)** addresses.

In `v0.11-mcp`, I added a minimal MCP client to my agent harness.

The result is surprisingly simple:

```text
External MCP Server
        │
        │ MCP / JSON-RPC
        ▼
   MCP Client
        │
        │ discovers tools
        ▼
   Agent Harness
        │
        ▼
       LLM
```

The important architectural decision is that an MCP tool gets converted into the **same** `(schema, callable)` **shape as the built-in tools**.

The agent loop doesn't need to know whether a tool is local or remote.

That is the key lesson of this version.

* * *

# What is MCP?

**Model Context Protocol (MCP)** is a standard protocol for connecting AI applications to external tools and other capabilities.

Instead of putting every tool implementation inside the agent application, we can run an external **MCP server** that exposes tools.

The agent application acts as the **MCP client**.

Conceptually:

```text
                    MCP
┌────────────────┐  protocol  ┌────────────────┐
│  Agent / Host   │◄──────────►│  MCP Server    │
│                │             │                │
│  MCP Client    │             │  Tools         │
└────────────────┘             └────────────────┘
```

The server owns the implementation.

The client discovers what the server provides and invokes those capabilities when needed.

This creates a clean separation:

```text
Agent harness
    ↓
MCP protocol
    ↓
External capability
```

* * *

# Why do AI agents need MCP?

Before MCP, my agent looked roughly like this:

```text
coding_agent.py
    │
    ├── list_files()
    ├── read_file()
    ├── write_file()
    ├── bash()
    ├── edit_file()
    ├── code_search()
    ├── remember()
    ├── list_skills()
    └── load_skill()
```

Every new integration meant modifying the harness.

Suppose I wanted GitHub access.

I could write:

```python
def github_create_issue(...):
    ...
```

Then add:

```text
schema
permission handling
execution
authentication
error handling
```

Then repeat the same process for:

```text
Slack
Postgres
Kubernetes
AWS
browser
Jira
```

The harness would gradually become a giant integration layer.

MCP changes the architecture.

Instead of implementing every integration inside the harness:

```text
                    Agent
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
     GitHub        Database       Browser
     code          code           code
```

we can have:

```text
                    Agent
                      │
                  MCP Client
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
    MCP Server     MCP Server     MCP Server
      GitHub        Database       Browser
```

The agent harness doesn't need to implement each service itself.

* * *

# How does an MCP client work?

For this lesson, I implemented only the minimal MCP flow needed to understand the protocol.

The important operations are:

```text
initialize
tools/list
tools/call
```

The complete lifecycle is:

```text
1. Start MCP server
        ↓
2. initialize
        ↓
3. initialized notification
        ↓
4. tools/list
        ↓
5. Convert tools into agent schemas
        ↓
6. LLM selects a tool
        ↓
7. tools/call
        ↓
8. Return result to LLM
```

Let's look at each step.

* * *

# 1\. Start the MCP server

The client launches the server as a subprocess.

In this lesson:

```python
self.proc = subprocess.Popen(
    self.command,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,
)
```

The client and server communicate through:

```text
stdin
stdout
```

This is the **stdio transport**.

The client writes requests to the server's stdin.

The server writes responses to stdout.

* * *

# What is the MCP stdio transport?

The transport used in this lesson is intentionally simple.

Messages are:

> newline-delimited JSON-RPC 2.0 messages

So communication looks conceptually like:

```text
Server stdin (client writes)
     │
     │ {"jsonrpc":"2.0", ...}
     ▼
MCP server
     │
     │ {"jsonrpc":"2.0", ...}
     ▼
Server stdout (client reads)
```

There is no HTTP server involved in this implementation.

There is no socket management.

There is no MCP SDK.

Just a subprocess and JSON messages.

That makes the protocol mechanics easy to inspect.

* * *
# 2\. Initialize the MCP connection

The first request is:

```text
initialize
```

The client sends:

```python
self._request(
    "initialize",
    {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {
            "name": "agents-zero-2-hero",
            "version": "0.11"
        },
    },
)
```

The server responds with information about itself and its capabilities.

The example server returns:

```json
{
  "protocolVersion": "2024-11-05",
  "capabilities": {
    "tools": {}
  },
  "serverInfo": {
    "name": "echo-server",
    "version": "0.1"
  }
}
```

The purpose of this handshake is to establish that the client and server can communicate and to exchange protocol/capability information.

* * *

# 3\. Send the initialized notification

After initialization, the client sends:

```text
notifications/initialized
```

Unlike a request, a notification does not require a response.

The client implementation represents that with:

```python
self._notify("notifications/initialized")
```

So the initial connection becomes:

```text
Client                         Server

   initialize  ────────────────►
                ◄───────────────  response

   initialized ────────────────►
```

Now the client can ask what tools the server provides.

* * *

# 4\. Discover tools with `tools/list`

This is one of the most important operations.

The client calls:

```python
tools = client.list_tools()
```

which sends:

```text
tools/list
```

The server returns tool definitions.

Our example server exposes two:

```text
echo
add
```

The definitions include:

```text
name
description
inputSchema
```

For example:

```json
{
  "name": "add",
  "description": "Add two numbers and return the sum.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "a": {
        "type": "number"
      },
      "b": {
        "type": "number"
      }
    },
    "required": [
      "a",
      "b"
    ]
  }
}
```

Notice something important.

The MCP server isn't just saying:

```text
I have an add function.
```

It also provides the schema that an LLM needs to call it correctly.

* * *

# Why tool discovery matters

This means the client doesn't need to know the tools in advance.

Before connecting:

```text
Agent
  │
  └── I don't know what this server provides.
```

After:

```text
tools/list
  │
  ▼
echo
add
```

The external server effectively becomes a dynamically discoverable tool provider.

This is one of the reasons protocols like MCP are useful for agent systems.

* * *

# 5\. Convert MCP tools into normal agent tools

Now comes the most important part of this implementation.

My agent already understands OpenAI-style function tools.

It expects something like:

```python
{
    "type": "function",
    "function": {
        "name": "...",
        "description": "...",
        "parameters": {...}
    }
}
```

I don't want to modify the agent loop just because a tool came from MCP.

So `mcp_client.py` provides:

```python
to_openai_schemas()
```

It converts:

```text
MCP tool definition
```

into:

```text
OpenAI function-tool schema
```

For example:

```text
MCP:

add
 ├── description
 └── inputSchema

        ↓

OpenAI-style:

mcp__add
 ├── description
 └── parameters
```

The resulting schema looks conceptually like:

```json
{
  "type": "function",
  "function": {
    "name": "mcp__add",
    "description": "Add two numbers and return the sum.",
    "parameters": {
      "type": "object",
      "properties": {
        "a": {
          "type": "number"
        },
        "b": {
          "type": "number"
        }
      },
      "required": [
        "a",
        "b"
      ]
    }
  }
}
```

This is a powerful architectural boundary.

* * *

# The agent loop doesn't need to know about MCP

This was the design goal.

The existing agent loop already does:

```python
response = client.chat.completions.create(
    model=model,
    messages=messages,
    tools=schemas,
)
```

Now `schemas` can contain:

```text
built-in tools
+
MCP tools
```

The model sees one unified tool list.

If it chooses:

```text
mcp__add
```

the harness looks up the corresponding callable.

The MCP implementation handles the remote call.

The agent loop doesn't need a special branch like:

```python
if tool_name.startswith("mcp__"):
    ...
```

That would couple the agent loop to MCP.

Instead, the MCP layer adapts itself to the existing tool abstraction.

* * *

# Why namespace MCP tools?

The external tools are prefixed with:

```text
mcp__
```

So:

```text
add
```

becomes:

```text
mcp__add
```

Why?

Because tool names can collide.

Suppose the local harness already has:

```python
add()
```

and an MCP server also exposes:

```text
add
```

Without namespacing, the two could conflict.

With namespacing:

```text
add
mcp__add
```

the source is obvious.

The convention also makes debugging easier:

```text
Tool call: mcp__add
```

immediately tells us that this isn't a built-in tool.

* * *

# 6\. Create proxy functions

Schemas alone aren't enough.

The LLM needs to call something.

That's what:

```python
make_proxies()
```

does.

Conceptually:

```text
LLM tool name
     │
     ▼
mcp__add
     │
     ▼
local proxy function
     │
     ▼
MCPClient.call_tool()
     │
     ▼
tools/call
     │
     ▼
MCP server
```

The proxy looks roughly like:

```python
def _proxy(_real=real_name, **kwargs):
    return client.call_tool(_real, kwargs)
```

So when the harness executes:

```python
tools_map["mcp__add"](a=21, b=21)
```

the proxy sends:

```text
tools/call
{
    "name": "add",
    "arguments": {
        "a": 21,
        "b": 21
    }
}
```

to the MCP server.

* * *

# The complete MCP tool flow

Putting everything together:

```text
                    LLM
                     │
              chooses mcp__add
                     │
                     ▼
              Agent harness
                     │
              tools_map lookup
                     │
                     ▼
               local proxy
                     │
                     ▼
                MCPClient
                     │
               JSON-RPC request
                     │
                     ▼
             ┌────────────────┐
             │  MCP Server    │
             │                │
             │  tools/call    │
             │      │         │
             │      ▼         │
             │    add(21,21)  │
             └──────┬─────────┘
                    │
                    ▼
                   "42"
                    │
                    ▼
               MCPClient
                    │
                    ▼
               Agent harness
                    │
                    ▼
                    LLM
```

From the LLM's perspective, this is just another tool call.

* * *

# The example MCP server

To make the lesson completely self-contained, the repository includes:

```text
mcp_servers/
└── echo_server.py
```

It uses only the Python standard library.

It exposes two tools:

```text
echo(text)
add(a, b)
```

The server implements three important MCP methods:

```python
if method == "initialize":
    ...

if method == "tools/list":
    ...

if method == "tools/call":
    ...
```

This is intentionally tiny.

The goal isn't to build a useful server.

The goal is to make the protocol visible.

* * *

# You can inspect the protocol directly

The example server can be started manually.

For example:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | python mcp_servers/echo_server.py
```

The response contains the available tools.

This is a useful exercise because it removes the LLM from the equation entirely.

You're seeing the protocol directly:

```text
JSON
  ↓
JSON-RPC
  ↓
MCP server
  ↓
tool definitions
```

That separation is important when debugging real agent systems.

* * *

# Running the agent with MCP

The demo is enabled using:

```bash
AGENT_MCP=1 python coding_agent.py
```

The agent starts the example MCP server and discovers:

```text
[mcp] connected; tools: ['echo', 'add']
```

The task then asks the model to use:

```text
mcp__add
```

with:

```text
21 + 21
```

The resulting flow is:

```text
LLM
 ↓
mcp__add(21, 21)
 ↓
MCPClient
 ↓
echo_server.py
 ↓
42
 ↓
LLM
 ↓
finish
```

The interesting part is that `coding_agent.py` didn't implement an `add()` function.

The capability came from another process.

* * *

# Why the MCP server is a separate process

The separation is important.

The server isn't merely another Python module imported by the agent.

It is a separate process:

```text
Agent process
      │
      │ stdin/stdout
      │
      ▼
MCP server process
```

That creates a useful architectural boundary.

The external server can:

*   have its own dependencies
    
*   have its own lifecycle
    
*   expose multiple tools
    
*   be implemented in another language
    
*   evolve independently of the agent harness
    

The client only needs to understand the protocol.

* * *

# MCP is more than just tool calling

This lesson intentionally implements only a small part of MCP.

The project focuses on:

```text
initialize
tools/list
tools/call
```

MCP itself supports a broader protocol model, including other capabilities and transports.

For this first implementation, I deliberately avoided building all of that.

The goal is to understand the fundamental abstraction:

> **An agent can connect to an external server, discover capabilities, and invoke them through a standard protocol.**

Once that abstraction is clear, richer MCP features become much easier to reason about.

* * *

# How does MCP differ from the skills from v0.10?

The previous version introduced **skills**.

Skills provide reusable knowledge:

```text
SKILL.md
   ↓
load_skill()
   ↓
knowledge
```

MCP provides external capabilities:

```text
MCP server
   ↓
tools/list
   ↓
tools/call
   ↓
action
```

A useful distinction is:

```text
Skills
  → "Here is how you should do something."

MCP tools
  → "Here is something you can do."
```

For example:

```text
python-style skill
    ↓
guidance for writing Python

GitHub MCP server
    ↓
create issue
read repository
open pull request
```

One supplies knowledge.

The other supplies capabilities.

* * *

# MCP tools still go through the agent's governance layer

There is an important security detail in this implementation.

The MCP tools aren't automatically treated as trusted.

When the agent chooses:

```text
mcp__add
```

the tool still goes through:

```text
permission check
      ↓
pre-hook
      ↓
execution
      ↓
post-hook
```

The architecture remains:

```text
LLM
 ↓
tool selection
 ↓
PermissionChecker
 ↓
PreToolUse
 ↓
MCP proxy
 ↓
MCP server
 ↓
result
 ↓
PostToolUse
 ↓
LLM
```

This preserves the governance architecture built in earlier lessons.

* * *

# Why are MCP tools not automatically read-only?

The project makes a conservative choice.

The permission system has a read-only allowlist.

MCP tools are **not** automatically added to that list.

Why?

Because the harness doesn't know what a foreign MCP tool actually does.

Consider an external tool called:

```text
delete_database
```

The harness shouldn't assume:

```text
"external tool" = safe
```

Instead, the safe default is:

```text
foreign capability
        ↓
not trusted automatically
        ↓
permission gate
```

This becomes particularly important when an MCP server provides tools that can modify external systems.

* * *

# Why this matters more with MCP

With local tools, you wrote the implementation.

You know what:

```python
write_file()
```

does.

With an external MCP server, the agent may receive:

```text
name
description
inputSchema
```

but the actual implementation lives somewhere else.

So the trust boundary changes.

The architecture becomes:

```text
                  Trust boundary
                       │
                       ▼
Agent harness ─── MCP protocol ─── External server
     │                                  │
     │                                  │
 permissions                         unknown
 hooks                               implementation
```

That means MCP makes the earlier permission and hook architecture even more important.

* * *

# Error handling in the MCP client

The client also handles JSON-RPC errors.

The `_request()` method sends a request with an ID:

```python
self._id += 1
```

and then waits for the matching response.

This matters because the client may encounter notifications or other messages.

The implementation reads lines until:

```python
data.get("id") == self._id
```

If the server returns:

```json
{
  "error": ...
}
```

the client raises:

```python
RuntimeError(...)
```

So a failed MCP request becomes a normal Python exception at the client boundary.

Again, the rest of the agent doesn't need to understand JSON-RPC.

* * *

# Why request IDs matter

JSON-RPC requests have IDs:

```text
request 1
request 2
request 3
```

The response carries the corresponding ID.

The client therefore knows:

```text
this response belongs to this request
```

In this minimal implementation, requests are handled sequentially.

A production implementation would need to think more carefully about:

*   concurrent requests
    
*   timeouts
    
*   server crashes
    
*   cancellation
    
*   message ordering
    
*   backpressure
    

But the fundamental correlation mechanism is already visible.

* * *

# Testing MCP without an LLM

One of my favorite parts of this implementation is that the MCP tests don't require an API key.

The tests launch the actual example server:

```python
self.client = MCPClient(SERVER).start()
```

and test the protocol directly.

For example:

```python
def test_call_add(self):
    out = self.client.call_tool(
        "add",
        {"a": 21, "b": 21}
    )

    self.assertEqual(
        out["content"][0]["text"],
        "42"
    )
```

There are also tests for:

```text
tool discovery
echo
add
errors
OpenAI schema conversion
proxy execution
```

Run them with:

```bash
python -m unittest tests.test_mcp -v
```

This is an important testing pattern for agent infrastructure:

> **Test protocol plumbing independently of model behavior.**

If MCP discovery is broken, I shouldn't need an LLM call to find out.

* * *

# What abstraction did we actually add?

It is tempting to describe this lesson as:

> “I added MCP.”

But that's not really the most important engineering change.

The more important abstraction is:

```text
external tool provider
        ↓
adapter
        ↓
existing tool interface
```

The agent already understands:

```text
schema + callable
```

So MCP becomes an adapter:

```text
MCP server
    │
    ├── tool definition
    │
    └── remote invocation
           │
           ▼
      MCP adapter
           │
           ▼
   schema + callable
           │
           ▼
      agent harness
```

This is classic adapter architecture.

* * *

# Why adapting is better than special-casing

A less clean implementation could have modified the agent loop:

```python
if tool_name.startswith("mcp__"):
    call_mcp(...)
elif tool_name.startswith("local__"):
    call_local(...)
```

That would work.

But every new tool provider would add another branch.

Instead:

```text
Agent loop
    │
    ▼
generic tool interface
    │
    ├── local callable
    ├── MCP proxy
    ├── future remote adapter
    └── future plugin adapter
```

The loop stays stable.

Only adapters change.

This is the same architectural principle that allowed skills, hooks, permissions, and providers to be added without rewriting the fundamental agent loop.

* * *

# The architecture after v0.11

The harness has now evolved substantially.

```text
                         ┌───────────────┐
                         │      LLM      │
                         └───────┬───────┘
                                 │
                          tool selection
                                 │
                                 ▼
                       ┌──────────────────┐
                       │   Tool registry  │
                       └────────┬─────────┘
                                │
                         Permission gate
                                │
                            Pre-hook
                                │
                            Execute
                                │
             ┌──────────────────┼──────────────────┐
             │                  │                  │
             ▼                  ▼                  ▼
        Built-in tools       Skills           MCP tools
             │                  │                  │
             │                  │                  ▼
             │                  │             MCP proxy
             │                  │                  │
             │                  │                  ▼
             │                  │            MCP server
             │                  │                  │
             └──────────────────┼──────────────────┘
                                │
                              result
                                │
                           Post-hook
                                │
                                ▼
                               LLM
```

And around this loop we now have:

```text
Memory
Compaction
Sessions
Permissions
Hooks
Skills
MCP
Provider abstraction
```

The project is starting to look less like a toy tool-calling script and more like an actual agent runtime.

* * *
# What MCP changes about the "agent harness"

The original harness was essentially:

```text
LLM + local tools
```

Now it becomes:

```text
LLM
 +
local tools
 +
external tools
 +
knowledge
 +
memory
 +
governance
 +
context management
```

This is an important conceptual shift.

The harness doesn't need to own every capability.

It needs to provide the **runtime that connects the model to capabilities safely and consistently**.

MCP is one mechanism for making that possible.

* * *

# What I deliberately did not build

This implementation is intentionally minimal.

It supports:

```text
stdio
JSON-RPC
initialize
tools/list
tools/call
```

It does not attempt to implement a complete production MCP client.

For example, a production implementation would need much more consideration around:

*   transport lifecycle
    
*   authentication
    
*   timeouts
    
*   cancellation
    
*   retries
    
*   concurrent requests
    
*   server health
    
*   capability negotiation
    
*   richer MCP capabilities
    
*   resource handling
    
*   prompt handling
    
*   security isolation
    

That's intentional.

This project is about understanding the primitives before hiding them behind a framework or SDK.

* * *

# A useful mental model for MCP

The simplest way I currently think about MCP is:

```text
MCP = standardized capability boundary
```

The agent doesn't need to know:

```text
how GitHub works
how PostgreSQL works
how Slack works
how Kubernetes works
```

It needs to know:

```text
what tools are available
what arguments they accept
how to invoke them
what result came back
```

The MCP server owns the implementation details.

The agent harness owns the orchestration and governance.

* * *

# v0.10 → v0.11

The progression between the last two versions is particularly useful.

In `v0.10`, the agent could acquire **knowledge**:

```text
skills/
    ↓
list_skills
    ↓
load_skill
    ↓
knowledge
```

In `v0.11`, the agent can acquire **capabilities**:

```text
MCP server
    ↓
tools/list
    ↓
tool schema
    ↓
tools/call
    ↓
external action
```

So:

```text
v0.10 = knowledge on demand

v0.11 = capabilities on demand
```

That distinction becomes increasingly important as agent systems grow.

* * *

# Where we are now

The journey has reached eleven components:

| Version | Capability | Problem solved |
| --- | --- | --- |
| `v0.1` | Tool calling | Agent can act |
| `v0.2` | File tools | Agent can inspect and modify files |
| `v0.3` | Bash | Agent can use a guarded shell |
| `v0.4` | Edit/search | Agent can make precise code changes |
| `v0.5` | Multi-provider | Agent isn't tied to one LLM provider |
| `v0.6` | Permissions | Agent actions have governance |
| `v0.7` | Hooks | Cross-cutting behavior around tools |
| `v0.8` | Memory | Agent can persist context |
| `v0.9` | Compaction | Agent can manage long conversations |
| `v0.10` | Skills | Agent can load reusable knowledge |
| `v0.11` | MCP | Agent can use externally hosted tools |

There is now a clear architecture emerging:

```text
                 AGENT HARNESS

    ┌──────────────────────────────────────┐
    │              Reasoning               │
    │                 LLM                  │
    ├──────────────────────────────────────┤
    │             Capabilities             │
    │  Local tools │ Skills │ MCP tools    │
    ├──────────────────────────────────────┤
    │              Governance              │
    │       Permissions │ Hooks             │
    ├──────────────────────────────────────┤
    │               Context                │
    │ Memory │ Sessions │ Compaction       │
    ├──────────────────────────────────────┤
    │              Providers               │
    │       OpenRouter │ DigitalOcean       │
    └──────────────────────────────────────┘
```

* * *

# What's next?

The next checkpoint is:

```text
v0.12-subagents
```

So far, we have one agent.

It can:

```text
reason
use tools
remember
load knowledge
connect to external tools
```

The next question is:

> **What if one agent isn't the right unit of work?**

Instead of doing everything itself, an agent could delegate a task to another agent:

```text
                 Main Agent
                     │
              delegate task
                     │
                     ▼
                Subagent
                     │
              tools + context
                     │
                     ▼
                  result
                     │
                     ▼
                 Main Agent
```

That moves the architecture from a single-agent tool loop toward **agent delegation and orchestration**.

* * *

# Final takeaway

The biggest lesson from `v0.11-mcp` isn't the JSON-RPC implementation.

It's the architectural boundary.

Before MCP:

```text
If I want a new capability,
I implement it inside my harness.
```

After MCP:

```text
If a server exposes the capability through a standard protocol,
my harness can discover and mount it.
```

The implementation is only a few building blocks:

```text
initialize
    ↓
tools/list
    ↓
adapt schemas
    ↓
create proxies
    ↓
tools/call
```

But those primitives create a much more extensible agent architecture.

The model doesn't need to know where a capability lives.

The harness doesn't need to implement every integration.

The MCP server owns the capability.

And the agent harness remains responsible for the part that matters most:

**deciding when to use a capability and enforcing the boundaries around that use.**

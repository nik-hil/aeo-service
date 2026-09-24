# Agents Zero to Hero #5: Making an AI Agent Provider-Agnostic

## Agents Zero to Hero #5: Making an AI Agent Provider-Agnostic

We've spent the first four checkpoints building the actual mechanics of an AI coding agent.

So far, the progression has been:

```text
v0.1 → tool calling
v0.2 → filesystem access
v0.3 → guarded shell + container
v0.4 → code search + precise editing
```

At this point, however, there is an architectural problem hiding outside the agent loop itself.

Our harness depends on an LLM provider.

Initially, the project was wired directly to OpenRouter.

That works.

But a reusable agent harness should ideally not care whether the model comes from:

```text
OpenRouter
DigitalOcean
another OpenAI-compatible provider
```

The important thing is the model interface.

That leads to `v0.5-multi-provider`.

Repository:

https://github.com/nik-hil/agents-zero-2-hero

* * *

# The key observation: the API is already standardized

Both providers used by this checkpoint expose an OpenAI-compatible API.

That means the Python SDK can remain the same.

Conceptually, the differences are only:

```text
base_url
API key
model identifier
```

The repository captures this explicitly.

The architecture becomes:

```text
                   Agent
                     │
                     ▼
              OpenAI SDK API
                     │
             ┌───────┴───────┐
             │               │
             ▼               ▼
        OpenRouter      DigitalOcean
```

The agent does not need to know which provider is underneath.

That is the entire point.

* * *

# Before v0.5

Earlier, `client.py` was effectively a single-provider client.

The code pointed at:

```text
https://openrouter.ai/api/v1
```

and used:

```text
OPENROUTER_API_KEY
```

The model was selected directly.

That creates coupling:

```text
coding_agent.py
       ↓
client.py
       ↓
OpenRouter
```

The goal now is:

```text
coding_agent.py
       ↓
client.py
       ↓
provider abstraction
       ↓
OpenRouter OR DigitalOcean
```

* * *

# The provider table

The new implementation introduces a provider configuration:

```python
PROVIDERS = {
    "openrouter": {
        "base_url":
            "https://openrouter.ai/api/v1",
        "api_key_env":
            "OPENROUTER_API_KEY",
        "default_model":
            "openai/gpt-5.6-luna",
    },

    "digitalocean": {
        "base_url":
            "https://inference.do-ai.run/v1",
        "api_key_env":
            "DIGITALOCEAN_INFERENCE_KEY",
        "default_model":
            "openai-gpt-5.6-luna",
    },
}
```

The important abstraction is:

```text
provider = {
    endpoint,
    credential,
    default model
}
```

The provider-specific details are now data rather than scattered conditionals.

* * *

# Why configuration as data is useful

Imagine implementing this with:

```python
if provider == "openrouter":
    ...
elif provider == "digitalocean":
    ...
```

That works for two providers.

But eventually:

```text
provider #3
provider #4
provider #5
```

makes the branching unpleasant.

With a provider registry:

```python
PROVIDERS = {
    ...
}
```

adding another compatible provider becomes closer to:

```python
PROVIDERS["provider_x"] = {...}
```

The architecture scales more naturally.

* * *

# Selecting the provider

The new helper is:

```python
def get_provider() -> str:
    return os.getenv(
        "LLM_PROVIDER",
        "openrouter"
    ).lower()
```

So:

```text
LLM_PROVIDER=openrouter
```

selects OpenRouter.

And:

```text
LLM_PROVIDER=digitalocean
```

selects DigitalOcean.

There is also a deliberate default:

```text
openrouter
```

for backward compatibility.

That is another useful configuration principle:

> New configuration should not unnecessarily break existing users.

* * *

# Validating the provider

The configuration resolver checks:

```python
if provider not in PROVIDERS:
    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. "
        f"Choose one of: {', '.join(PROVIDERS)}"
    )
```

This is a small but important detail.

Configuration errors should fail early and clearly.

Instead of producing a mysterious error later during an API call, the harness can tell us:

```text
Unknown LLM_PROVIDER='foo'
```

immediately.

* * *

# Selecting the model

The project also introduces:

```python
def get_model() -> str:
    return os.getenv(
        "LLM_MODEL"
    ) or _config()["default_model"]
```

This gives us a clean precedence model:

```text
LLM_MODEL
    ↓
explicit override

otherwise
    ↓
provider default
```

So the harness can use:

```text
provider default
```

for normal operation while still allowing developers to override the model when needed.

* * *

# Provider-specific model IDs

There is an interesting detail here.

The same conceptual model can have different identifiers at different providers.

The repository explicitly notes that DigitalOcean model identifiers use a different naming style from OpenRouter.

So we have:

```text
OpenRouter:
openai/gpt-5.6-luna

DigitalOcean:
openai-gpt-5.6-luna
```

That is exactly why model selection belongs in the provider configuration.

The agent shouldn't contain logic like:

```python
if provider == ...:
    model = ...
```

The provider layer owns that mapping for defaults. An explicit `LLM_MODEL` override takes precedence and is used as supplied, without translation by `get_model()`.

When switching providers, unset `LLM_MODEL` to use the new provider's default, or update it to an identifier for that provider.

* * *
# One client factory

The key abstraction is now:

```python
def get_client() -> OpenAI:
```

It resolves the configuration:

```python
cfg = _config()
```

retrieves the correct API key:

```python
api_key = os.getenv(
    cfg["api_key_env"]
)
```

and validates it:

```python
if not api_key:
    raise ValueError(...)
```

Then creates:

```python
return OpenAI(
    base_url=cfg["base_url"],
    api_key=api_key,
    default_headers={
        "X-Title":
            "Agents Zero 2 Hero"
    },
)
```

That means the rest of the application doesn't need to know anything about providers.

* * *

# The agent barely changes

This is the best part of the architecture.

The coding agent still does:

```python
client = get_client()
```

and:

```python
response = client.chat.completions.create(
    model=model,
    messages=messages,
    tools=TOOL_SCHEMAS,
    ...
)
```

There is no:

```python
if OpenRouter
```

and no:

```python
if DigitalOcean
```

inside the agent loop.

That is exactly what we wanted.

The dependency inversion is:

```text
Agent
  ↓
generic client interface
  ↓
provider implementation
```

rather than:

```text
Agent
  ↓
OpenRouter-specific implementation
```

* * *

# This is more than convenience

At first glance, multi-provider support can look like a deployment convenience.

But there is a deeper reason.

The agent harness should own:

```text
state
tools
permissions
execution
observability
reasoning loop
```

It should not own:

```text
where the model happens to run
```

Those are separate concerns.

* * *

# A useful architectural boundary

Think about the system as two layers.

### Harness layer

```text
agent loop
tool registry
tool schemas
workspace
permission policy
message history
execution
```

### Inference layer

```text
model provider
endpoint
authentication
model identifier
```

The interface between them is basically:

```text
chat completion + tool calling
```

That makes the model provider replaceable.

* * *

# This also enables experimentation

Once provider selection is centralized, we can start comparing:

```text
provider A
vs
provider B
```

without modifying the harness.

That becomes very useful when experimenting with agent behavior.

We might want to compare:

```text
latency
tool-calling reliability
cost
context limits
reasoning quality
structured output reliability
```

while keeping the agent implementation identical.

That turns the provider abstraction into an experimentation boundary.

* * *

# Configuration through `.env`

The repository expects configuration through environment variables.

For example:

```text
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
```

or:

```text
LLM_PROVIDER=digitalocean
DIGITALOCEAN_INFERENCE_KEY=...
```

The project uses:

```python
load_dotenv()
```

so local `.env` configuration works naturally.

This is also a good reminder:

> Credentials belong in environment configuration, not source code.

The repository README explicitly recommends keeping keys local and not putting them into commits, chat messages, or issues.

* * *

# The client now becomes an adapter

Architecturally, `client.py` is evolving into an adapter.

The agent thinks:

```text
Give me an LLM client.
```

The adapter determines:

```text
which provider?
which endpoint?
which credential?
which default model?
```

This is effectively a small Strategy/Adapter-style abstraction.

The implementation is intentionally simple because we don't need a heavyweight dependency-injection framework for a project this small.

* * *

# Why not create separate client classes?

We could implement:

```python
OpenRouterClient
DigitalOceanClient
```

and perhaps an abstract interface.

But at this scale, that would introduce more machinery than value.

Both providers already speak the same API style.

So a simple configuration map is enough:

```python
PROVIDERS = {...}
```

This is a useful design lesson:

> Don't introduce an abstraction more complicated than the variability you actually have.

* * *

# The provider abstraction also improves testing

Suppose the agent loop needs testing.

We don't necessarily care which provider executes the test.

We can treat the client as an injectable boundary and focus tests on:

```text
tool dispatch
message handling
finish semantics
iteration limits
error handling
permission enforcement
```

Provider integration can be tested separately.

That separation becomes increasingly valuable as the harness grows.

* * *

# The bigger lesson from v0.5

The previous checkpoints focused on **agent capabilities**.

This checkpoint focuses on **architectural boundaries**.

The project has now reached:

```text
                    ┌───────────────┐
                    │      LLM      │
                    └───────┬───────┘
                            │
                     inference API
                            │
                    ┌───────▼───────┐
                    │    Harness    │
                    │               │
                    │ tools         │
                    │ tool schemas  │
                    │ state         │
                    │ execution     │
                    │ workspace     │
                    └───────┬───────┘
                            │
                  provider abstraction
                            │
             ┌──────────────┴──────────────┐
             │                             │
             ▼                             ▼
        OpenRouter                  DigitalOcean
```

The model provider has become a replaceable component.

* * *

# One important repository-state note

There is an interesting discrepancy in the current repository state.

The actual Git tag exposed by the repository is:

```text
v0.5-multi-provider
```

and that tag contains the provider abstraction described in this article.

However, the current `master` `lessons.yml` describes the fifth roadmap checkpoint as:

```text
v0.5-permissions
```

with a `PermissionChecker`.

So the roadmap has evidently moved ahead or was renamed without the corresponding tag reference being updated.

For this article series, I would keep:

```text
v0.5-multi-provider
```

because the blog is intended to document what actually exists at that Git tag.

This also illustrates why tagging snapshots is so useful:

> A Git tag is a concrete historical contract. The current branch is not necessarily that contract.

* * *

# Where we are after five checkpoints

Let's summarize the journey.

## v0.1

```text
LLM
 ├── execute_code
 └── finish
```

Lesson:

> The agent loop is just model calls + tool dispatch + feedback.

* * *

## v0.2

```text
+ list_files
+ read_file
+ write_file
```

Lesson:

> Agents need an environment they can observe and manipulate.

* * *

## v0.3

```text
+ bash
+ workspace restrictions
+ container execution
```

Lesson:

> Powerful capabilities need execution boundaries.

* * *

## v0.4

```text
+ code_search
+ edit_file
```

Lesson:

> Agent capabilities should resemble how developers actually work.

* * *

## v0.5

```text
+ provider abstraction
+ model selection
+ OpenRouter
+ DigitalOcean
```

Lesson:

> Keep inference infrastructure separate from agent-harness logic.

* * *

# What I like about building the project this way

The temptation when learning agent systems is to start with:

```text
LangGraph
CrewAI
AutoGen
OpenAI Agents SDK
...
```

Those frameworks are useful.

But they also hide a lot.

A project like this makes you confront the underlying mechanics:

```text
What is a tool?
How does the model request one?
How do we execute it?
How is the result represented?
How does the next model call know what happened?
Where do permissions live?
Where does state live?
Where does security live?
What happens when a tool fails?
How do we swap models?
```

Once those concepts are clear, frameworks become much easier to understand.

You're no longer learning:

```text
framework API
```

You're mapping the framework API to concepts you already understand.

* * *

# Where the series goes next

Provider abstraction was not actually the most important capability I originally expected to add at this stage.

The more interesting next architectural step is governance.

The current project roadmap describes the next lesson as:

```text
PermissionChecker
```

with modes such as:

```text
ask
auto
plan
```

and policy rules for:

```text
paths
commands
tool calls
```

That is the natural evolution of what we started in `v0.3`.

We currently have permissions embedded inside individual tools:

```text
bash → allowlist
filesystem → path checks
```

The next step is to generalize that into:

```text
                Tool call
                    │
                    ▼
            ┌──────────────┐
            │  Permission  │
            │    layer     │
            └──────┬───────┘
                   │
             allowed?
             /      \
           yes       no
            │         │
            ▼         ▼
        execute     reject/ask
```

That is a much bigger architectural idea than simply adding another tool.

And that is exactly why I like the incremental Git-tag approach.

Each step introduces one new concept.

You can inspect the code.

You can run it.

You can understand the trade-off.

Then move to the next checkpoint.

* * *

## Repository

https://github.com/nik-hil/agents-zero-2-hero

Current tag:

```text
v0.5-multi-provider
```

The journey so far:

```text
Zero
 │
 ├── tool calling
 ├── filesystem
 ├── shell
 ├── precise editing
 └── provider abstraction
 │
 ▼
Hero
```

And we're only getting started.

# Agents Zero to Hero #10: Building On-Demand Skills for AI Agents

# Agents Zero to Hero #10: Building On-Demand Skills for AI Agents

An AI coding agent needs more than tools.

It also needs **knowledge**.

For example:

*   How should Python code be written in this project?
    
*   What is the team's commit convention?
    
*   How should a deployment be performed?
    
*   What testing strategy should be followed?
    
*   What architectural rules should the agent respect?
    

One obvious solution is to put all of these instructions into the system prompt.

But that doesn't scale.

If an agent has 50 different capabilities, putting all 50 sets of instructions into every request makes the context larger, noisier, and more expensive.

In **v0.10 of Agents Zero to Hero**, I added **on-demand skills**.

The idea is simple:

```text
System prompt
     │
     ├── Skill catalog
     │     ├── python-style
     │     ├── git-commit
     │     └── ...
     │
     ▼
Agent recognizes relevant skill
     │
     ▼
load_skill("python-style")
     │
     ▼
Full skill instructions
```

The agent knows **which knowledge is available**, but doesn't pay the cost of loading all of it into context.

This is the same basic principle behind many scalable agent systems:

> **Discover cheaply. Load deeply only when needed.**

* * *

# What problem do AI agent skills solve?

Imagine building an agent that knows how to work on a software project.

You might want to give it instructions for:

```text
Python style
Git conventions
Testing
Deployment
Database migrations
API design
Security
Documentation
Incident response
Cloud infrastructure
...
```

A naive implementation might put everything into the system prompt:

```text
SYSTEM PROMPT

You are a coding agent.

Here are the Python rules...
Here are the Git rules...
Here are the deployment rules...
Here are the database rules...
Here are the security rules...
Here are the documentation rules...
...
```

This creates a scaling problem.

If each skill contains 2,000 characters and you have 50 skills:

```text
50 × 2,000 = 100,000 characters
```

Most tasks don't need all of that knowledge.

If the user asks:

```text
"Create a Python utility."
```

the agent probably needs the Python conventions.

It probably doesn't need:

```text
Kubernetes deployment runbook
database migration procedure
incident response guide
```

So instead of loading everything, we separate **discovery** from **execution**.

* * *

# What is an AI agent skill?

In this implementation, a skill is simply a Markdown file containing reusable guidance.

The structure is:

```text
skills/
├── python-style/
│   └── SKILL.md
└── git-commit/
    └── SKILL.md
```

A skill file looks like this:

```markdown
---
name: python-style
description: How to write clean, idiomatic Python for this project.
---

# Python style

Write clean, idiomatic Python.

Prefer small functions.
Use descriptive names.
Avoid unnecessary abstractions.
...
```

There are two distinct parts:

```text
Frontmatter
    ↓
metadata about the skill

Body
    ↓
actual instructions
```

The metadata is cheap.

The body can be expensive.

That distinction is the foundation of the design.

* * *

# Why not just inject every skill into the system prompt?

Because the agent doesn't need every skill for every task.

Consider an agent with these skills:

```text
python-style
git-commit
docker-deploy
kubernetes-operations
database-migration
security-review
api-design
incident-response
```

Now imagine the user asks:

```text
Create a Python function that parses a configuration file.
```

The relevant knowledge might be:

```text
python-style
```

Loading everything would create unnecessary context.

Instead, the agent initially sees:

```text
Available skills:

- python-style: How to write clean, idiomatic Python for this project.
- git-commit: How to create commits following project conventions.
- docker-deploy: How to build and deploy Docker images.
- kubernetes-operations: Kubernetes operational procedures.
...
```

That's tiny compared with the full contents.

Then:

```text
Agent
  ↓
Recognizes python-style is relevant
  ↓
load_skill("python-style")
  ↓
Receives full instructions
```

This is **on-demand context loading**.

* * *

# What is the architecture of the skill system?

The implementation introduces a `SkillLibrary`.

Conceptually:

```text
                 ┌───────────────────┐
                 │     skills/       │
                 ├───────────────────┤
                 │ python-style/     │
                 │   SKILL.md        │
                 │                   │
                 │ git-commit/       │
                 │   SKILL.md        │
                 └─────────┬─────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  SkillLibrary   │
                  └────────┬────────┘
                           │
                ┌──────────┴──────────┐
                │                     │
                ▼                     ▼
         catalog()              load(name)
                │                     │
                ▼                     ▼
       name + description       full skill body
```

The important design decision is that `SkillLibrary` discovers skills once, but doesn't need to load all skill bodies into the agent's context.

* * *

# How does SkillLibrary discover skills?

The implementation looks under:

```text
skills/<name>/SKILL.md
```

For example:

```text
skills/
├── python-style/
│   └── SKILL.md
├── git-commit/
│   └── SKILL.md
└── deployment/
    └── SKILL.md
```

`SkillLibrary` scans the directory and builds an in-memory registry.

Each discovered skill becomes a small object containing:

```python
@dataclass
class Skill:
    name: str
    description: str
    path: Path
```

Notice what isn't stored here:

```text
full skill body
```

The body stays on disk until the skill is actually loaded.

That's intentional.

* * *

# How does the skill frontmatter work?

The skill file uses a lightweight Markdown frontmatter format:

```markdown
---
name: python-style
description: How to write clean, idiomatic Python for this project.
---
# Python style

...
```

The implementation has a small parser:

```python
def _parse_frontmatter(text: str) -> tuple[dict, str]:
    ...
```

It separates:

```text
---
name: ...
description: ...
---
```

from the rest of the document.

The result is effectively:

```python
meta = {
    "name": "python-style",
    "description": "How to write clean, idiomatic Python for this project."
}

body = """
# Python style

...
"""
```

This keeps the format simple.

There is no database.

No registry service.

No special serialization format.

Just Markdown files.

* * *

# Why use Markdown for skills?

Because skills are primarily **human-authored knowledge**.

Markdown is useful because:

*   developers already know how to write it,
    
*   it is easy to review in Git,
    
*   it can contain code examples,
    
*   it can contain headings and lists,
    
*   it can be edited without changing Python code,
    
*   it works naturally with documentation workflows.
    

Most importantly, a skill becomes a normal project artifact.

For example:

```text
skills/python-style/SKILL.md
```

can be reviewed in a pull request just like:

```text
README.md
```

or:

```text
docs/architecture.md
```

This makes agent knowledge version-controlled.

* * *

# What does the agent see initially?

The agent receives a **skill catalog**.

For example:

```text
# Available skills (load with load_skill)

- python-style: How to write clean, idiomatic Python for this project.
- git-commit: How to create commits following project conventions.
```

This is intentionally small.

The implementation exposes:

```python
def catalog(self) -> list[dict]:
    return [
        {
            "name": s.name,
            "description": s.description
        }
        for s in self.skills.values()
    ]
```

And then:

```python
def catalog_text(self) -> str:
    return "\n".join(
        f"- {s['name']}: {s['description']}"
        for s in self.catalog()
    )
```

The catalog is injected into the system prompt.

So the model knows what is available without receiving every skill's contents.

* * *

# What happens when the agent needs a skill?

Two new tools are introduced:

```text
list_skills
load_skill
```

`list_skills` returns the catalog:

```json
{
  "skills": [
    {
      "name": "python-style",
      "description": "How to write clean, idiomatic Python for this project."
    },
    {
      "name": "git-commit",
      "description": "How to create commits following project conventions."
    }
  ]
}
```

Then the agent can call:

```text
load_skill("python-style")
```

The tool returns:

```json
{
  "name": "python-style",
  "content": "# Python style\n..."
}
```

The full body enters the conversation only when it is needed.

* * *

# What does the complete interaction look like?

Suppose the user asks:

```text
Create greet.py with a Python function that returns a greeting.
```

The agent starts with:

```text
Available skills:

python-style
git-commit
```

The model recognizes that `python-style` is relevant.

It calls:

```text
list_skills()
```

and then:

```text
load_skill("python-style")
```

The skill content becomes available to the model.

The agent can then create:

```python
def greet(name):
    return f"Hello, {name}!"
```

The important point is that the agent didn't receive the entire knowledge base up front.

It retrieved the relevant knowledge when required.

* * *

# Why is the catalog so important?

It may look like an unnecessary extra step.

Why not just let the model guess the file path?

Because the catalog creates a clean abstraction boundary.

The model interacts with:

```text
skill name
skill description
```

rather than:

```text
filesystem path
```

This means the storage layout can change without changing the agent's conceptual interface.

Today:

```text
skills/python-style/SKILL.md
```

Tomorrow the implementation could potentially load skills from:

```text
database
remote service
Git repository
package
```

while keeping the agent interface:

```text
list_skills()
load_skill(name)
```

That is a useful separation of concerns.

* * *

# Why is loading a skill a read-only operation?

A skill is knowledge.

Loading it doesn't modify the workspace.

The two skill tools therefore don't need write permissions.

This matters because the agent already has a permission system from **v0.6**.

The new tools can safely be allowed in restrictive modes because:

```text
list_skills
    ↓
read-only

load_skill
    ↓
read-only
```

They don't:

```text
write files
execute commands
modify the workspace
```

This makes skills a relatively low-risk extension to the agent's toolkit.

* * *

# How does v0.10 interact with context compaction?

This is where v0.9 and v0.10 connect directly.

In v0.9, we introduced context compaction because long conversations consume context.

Now imagine we solve the problem by putting every skill into the system prompt.

We would immediately make the context problem worse.

For example:

```text
50 skills
    ↓
all injected into prompt
    ↓
huge context
    ↓
compaction
    ↓
skill information may be summarized away
```

That's exactly what we don't want.

Instead:

```text
skill catalog
    ↓
small context footprint
    ↓
load relevant skill
    ↓
use it
```

This is why the v0.10 design builds naturally on v0.9.

**Compaction manages accumulated conversation.**

**Skills manage reusable knowledge.**

* * *

# Why aren't skills just memory?

This is another important distinction.

At first glance, a skill file looks similar to `MEMORY.md`.

But they represent different kinds of information.

### Memory

Memory contains facts discovered or recorded for a particular project or run.

For example:

```text
The project uses PostgreSQL.
The API runs on port 8080.
The user prefers pytest.
```

Memory answers:

> What should I remember?

### Skills

Skills contain reusable instructions.

For example:

```text
Use type hints.
Prefer small functions.
Write unit tests for public APIs.
Follow this commit convention.
```

Skills answer:

> How should I perform this kind of work?

So:

```text
Memory → facts/context
Skills → reusable procedures/guidance
```

That distinction becomes increasingly important as agents become more capable.

* * *

# What happens if a skill doesn't exist?

The implementation handles this explicitly.

If the model asks:

```text
load_skill("kubernetes")
```

but the skill isn't available, the result is:

```json
{
  "error": "unknown skill: kubernetes",
  "available": [
    "python-style",
    "git-commit"
  ]
}
```

This is preferable to silently returning an empty result.

The model gets enough information to recover:

```text
requested skill doesn't exist
        ↓
see available skills
        ↓
choose another approach
```

* * *

# What happens if the skills directory doesn't exist?

The library handles that too.

If:

```text
skills/
```

doesn't exist, the library simply has no skills.

The tests explicitly cover this behavior.

This keeps skills optional.

An agent can still run without a skill library.

* * *

# How do you add a new skill?

This is one of the useful properties of the design.

You don't need to modify `coding_agent.py`.

Create:

```text
skills/my-skill/SKILL.md
```

For example:

```markdown
---
name: api-design
description: Guidelines for designing HTTP APIs in this project.
---

# API design

Use resource-oriented URLs.

Return consistent error responses.

Version breaking API changes.

...
```

Restart the agent.

The library discovers it automatically.

The catalog now contains:

```text
- api-design: Guidelines for designing HTTP APIs in this project.
```

No new Python code is required.

That's an important architectural property:

> **Adding knowledge should not require modifying the agent runtime.**

* * *

# What does this look like in the agent architecture?

The agent now has several different sources of capability:

```text
                    ┌────────────────────┐
                    │    System Prompt   │
                    └─────────┬──────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
       Memory             Skills              Tools
          │                   │                   │
          │            ┌──────┴──────┐            │
          │            │             │            │
          │        catalog       full body       │
          │            │          on demand      │
          │            │                         │
          └────────────┴──────────────┬──────────┘
                                      │
                                      ▼
                                  LLM loop
```

The distinction is becoming clearer:

```text
Tools   → things the agent can do
Memory  → things the agent remembers
Skills  → ways the agent should perform certain work
```

This separation makes the architecture easier to reason about.

* * *

# Why are skills useful for agent architecture?

Without skills, every new behavior tends to end up in one of three places:

```text
1. System prompt
2. Python code
3. Tool implementation
```

That creates coupling.

Suppose you want to teach the agent your team's deployment process.

Without skills, you might modify the system prompt:

```text
If deploying:
  step 1...
  step 2...
  step 3...
```

Now deployment knowledge is embedded inside agent runtime configuration.

With skills:

```text
skills/deployment/SKILL.md
```

The knowledge is separated from the execution engine.

That means:

```text
Agent runtime
       +
Reusable knowledge
```

can evolve independently.

* * *

# Skills are a form of context modularity

This is perhaps the most important conceptual takeaway from v0.10.

A large agent doesn't need one giant prompt.

It can have modular context:

```text
                    Agent
                      │
             ┌────────┴────────┐
             │                 │
          Catalog           Tools
             │
      ┌──────┼──────┐
      │      │      │
   Python   Git   Deploy
      │      │      │
      ▼      ▼      ▼
    Load   Load   Load
    when   when   when
    needed needed needed
```

This is similar to modular software design.

Instead of:

```text
one giant module
```

you get:

```text
small modules
+
explicit interfaces
+
load when required
```

The same principle works for agent context.

* * *

# What are the tradeoffs?

On-demand skills solve a context-scaling problem, but they introduce new considerations.

## Benefit: smaller default context

The agent only receives:

```text
name + description
```

for each skill.

That's cheap compared with loading every body.

## Benefit: easy extensibility

Adding a skill doesn't require changing the agent loop.

Just add a Markdown file.

## Benefit: human-readable knowledge

Developers can review and edit skills directly.

## Cost: the model must choose correctly

The model needs to recognize that a particular skill is relevant.

If the description is poor, it may never load the skill.

For example:

```text
name: python-style
description: Useful stuff
```

is much worse than:

```text
name: python-style
description: How to write clean, idiomatic Python for this project.
```

The catalog description becomes part of the model's decision-making interface.

## Cost: loaded skills consume context

On-demand doesn't mean free.

Once a skill is loaded, its content occupies context.

If an agent loads ten large skills, it can still create context pressure.

So the design changes the problem from:

```text
load everything
```

to:

```text
discover everything
load selectively
```

That's a significant improvement, but not a complete solution.

* * *

# What would a production skill system need?

The v0.10 implementation intentionally stays small.

A production implementation could add several capabilities.

### Skill ranking

Instead of asking the model to decide entirely from descriptions:

```text
task
  ↓
skill retrieval
  ↓
top relevant skills
```

A semantic search or embedding-based system could rank skills.

### Skill dependencies

A skill could depend on another:

```text
deployment
    ↓
docker
    ↓
python
```

The runtime could resolve those dependencies.

### Skill versioning

Skills could have explicit versions:

```text
python-style@v2
```

This becomes useful when behavior changes over time.

### Skill validation

The repository could validate:

```text
required frontmatter
unique names
description length
missing bodies
invalid files
```

### Skill scopes

Some skills might apply globally:

```text
python-style
```

while others might apply only to:

```text
project
repository
directory
language
task
```

### Tool-linked skills

A skill could explicitly declare tools it expects:

```text
deployment skill
    ↓
requires:
  bash
  docker
```

The agent could then reason about both knowledge and capabilities.

* * *

# What does v0.10 teach about agent design?

The interesting part isn't the Markdown parser.

It's the separation between:

```text
knowledge availability
```

and:

```text
knowledge consumption
```

A scalable agent shouldn't have to load everything it knows before every task.

Instead:

```text
Discover
   ↓
Select
   ↓
Load
   ↓
Apply
```

This is a pattern that can be reused far beyond skills.

The same architecture can apply to:

*   documentation,
    
*   API specifications,
    
*   coding conventions,
    
*   runbooks,
    
*   domain knowledge,
    
*   organizational policies,
    
*   project instructions.
    

* * *

# How v0.10 fits into the series

The agent has now evolved through several layers.

```text
v0.1  Basic agent loop
        ↓
v0.2  File tools
        ↓
v0.3  Guarded shell
        ↓
v0.4  Precise editing/search
        ↓
v0.5  Multiple providers
        ↓
v0.6  Permissions
        ↓
v0.7  Hooks
        ↓
v0.8  Persistent memory
        ↓
v0.9  Context compaction
        ↓
v0.10 On-demand skills
```

There is now a useful division:

```text
Tools
  → What can the agent do?

Memory
  → What does the agent remember?

Compaction
  → What context can the agent afford to keep?

Skills
  → What reusable knowledge can the agent load?
```

These are different primitives.

Keeping them separate makes the overall agent easier to extend.

* * *

# Try it yourself

Run the agent normally:

```bash
python coding_agent.py
```

The demo task asks the agent to list its available skills, load `python-style`, and create `greet.py` following that skill.

You should see the flow:

```text
[skills] 2 available: python-style, git-commit

Tool call: list_skills ...

Tool call: load_skill
{'name': 'python-style'}

Tool call: write_file ...
```

You can also run the dedicated tests:

```bash
python -m unittest tests.test_skills -v
```

And adding another skill is as simple as:

```text
skills/
└── my-skill/
    └── SKILL.md
```

No agent-loop code needs to change.

* * *

# Key takeaways

### 1\. Don't put every instruction into the system prompt

Large collections of knowledge make every request more expensive.

### 2\. Separate discovery from loading

The agent can see:

```text
skill name + description
```

without seeing:

```text
full skill body
```

until it needs it.

### 3\. Skills are reusable knowledge

They are different from tools and different from persistent memory.

```text
Tool   → action
Memory → fact
Skill  → guidance
```

### 4\. Markdown makes knowledge version-controlled

A skill can be reviewed, modified, and shared like any other project file.

### 5\. On-demand loading improves context scalability

Instead of:

```text
all knowledge → every request
```

we get:

```text
catalog → relevant knowledge → current request
```

### 6\. The catalog is part of the agent interface

The description isn't just documentation.

It helps the model decide **when a skill should be loaded**.

Good descriptions therefore matter.

* * *

# What's next?

The agent now has a growing toolkit.

It can:

```text
read/write files
run guarded commands
edit code
search code
remember information
compact context
load reusable skills
```

But there is another problem.

Modern AI systems increasingly need to connect agents to **external tool ecosystems**.

Instead of hard-coding every integration directly into the agent:

```text
Agent
 ├── GitHub tool
 ├── Database tool
 ├── Slack tool
 ├── Browser tool
 ├── ...
```

what if the agent could connect to an external protocol and discover tools dynamically?

That's the problem addressed in the next stage of the series:

**MCP — the Model Context Protocol.**

* * *

## Source code

The implementation for this lesson is available in the `v0.10-skills` tag:

https://github.com/nik-hil/agents-zero-2-hero/tree/v0.10-skills

Important files:

*   `skills.py` — `SkillLibrary`, discovery, catalog, and on-demand loading
    
*   `coding_agent.py` — skill tools and catalog injection
    
*   `skills/python-style/SKILL.md` — example Python skill
    
*   `skills/git-commit/SKILL.md` — example Git skill
    
*   `tests/test_skills.py` — skill discovery and loading tests
    

* * *

## Series

This is **Lesson 10** in my *Agents Zero to Hero* series.

The goal is to build an AI coding agent from first principles, one capability at a time, and understand the engineering primitives underneath modern agentic systems.

No framework magic.

Just:

```text
LLM
 ↓
Tool
 ↓
Result
 ↓
State
 ↓
LLM
 ↓
Repeat
```

One git tag at a time.

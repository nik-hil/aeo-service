---
title: "Agents Zero to Hero: Tool Calling Basics"
tags: agents, llm, tool-calling
canonical_url: https://blog.example.com/agents-zero-to-hero-tool-calling
---

# Agents Zero to Hero: Tool Calling Basics

Building an AI agent sounds deceptively simple. Call an LLM, give it a prompt, get an answer. But that is not really an agent.

An LLM becomes an agent when it can decide to take actions, invoke capabilities outside the model, observe the result, and continue until the task is complete.

This article explains the agent loop and a minimal tool-calling harness from first principles.

```python
# Not a real heading — fence must be ignored:
# ## Fake Heading Inside Fence
while True:
    response = client.chat.completions.create(messages=messages, tools=TOOLS)
    if not response.tool_calls:
        break
```

## What is an agent loop?

The agent loop is the control flow that lets a model call tools, see results, and decide whether to continue. At a high level the model proposes an action, the harness executes it, and the observation is appended to the conversation.

Without an explicit loop, tool calling is just a one-shot function invocation with no follow-through.

## How tool calling works

Tool calling works by giving the model a schema of available functions. The model returns a structured tool call instead of (or before) a final answer. The host runs the function and returns the result as another message.

Schemas should describe arguments precisely so the model can fill them without guessing.

## Choosing tools for a harness

A minimal harness needs a small set of tools: read a file, write a file, and run a shell command. More tools can wait until the loop and permissions model are solid.

Avoid exposing unbounded network access before you have a permission gate.

## Common failure modes

Common failure modes include hallucinated tool names, missing required arguments, and infinite loops when the model never emits a stop condition. Logging each tool call and capping iterations prevents runaway sessions.

## Next steps

Next steps are filesystem tools, shell execution with sandboxing, and a provider abstraction so the same loop works across models.

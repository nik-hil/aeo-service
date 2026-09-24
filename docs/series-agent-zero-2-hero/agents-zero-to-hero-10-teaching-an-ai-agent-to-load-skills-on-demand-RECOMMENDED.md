# Agents Zero to Hero #10: Teaching an AI Agent to Load Skills on Demand

## Agents Zero to Hero #10: Teaching an AI Agent to Load Skills on Demand

AI agents can use tools, remember information, and manage long conversations.

But there is another problem.

**What happens when the agent needs specialized knowledge that is too large to keep in every prompt?**

A coding agent might need to know:

*   the project's Python coding conventions
    
*   how commits should be structured
    
*   deployment procedures
    
*   incident-response runbooks
    
*   API conventions
    
*   database migration rules
    
*   testing requirements
    
*   company-specific engineering practices
    

You could put all of this into the system prompt.

But that doesn't scale.

If an agent has 30 different pieces of domain knowledge, putting all 30 into every request makes the context larger, more expensive, and potentially less focused.

In `v0.10-skills`, the agent gets a new capability:

> **Discover available skills cheaply, then load the full instructions only when the current task needs them.**

The implementation uses simple Markdown files and two tools:

```text
list_skills()
load_skill(name)
```

No vector database.

No embeddings.

No framework.

Just files, metadata, and an o

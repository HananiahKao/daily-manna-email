# Session Context

## User Prompts

### Prompt 1

Well, I want to synthesize an improvement plan for this repo. The first thing that comes to my mind is that I want to improve the dashboard's UX, but it's too vague, and I want to be able to let ordinary subscribers subscribe. We have a subscriber DB, but it's not currently used in production, so that's the first thing that I would change, and it lasted so long. Maybe we could expand to more channels, but we should list them by p-value and s-value, so priority and severity, I think. Expanding mo...

### Prompt 2

# Update Config Skill

Modify Claude Code configuration by updating settings.json files.

## When Hooks Are Required (Not Memory)

If the user wants something to happen automatically in response to an EVENT, they need a **hook** configured in settings.json. Memory/preferences cannot trigger automated actions.

**These require hooks:**
- "Before compacting, ask me what to preserve" → PreCompact hook
- "After writing files, run prettier" → PostToolUse hook with Write|Edit matcher
- "When I run...

### Prompt 3

/bash ls /Users/hananiah/Developer/markdown-tools/

### Prompt 4

/bash /Users/hananiah/Developer/markdown-tools/md-to-html-converter.py IMPROVEMENT_PLAN.md

### Prompt 5

Inside the MD file, add a comprehensive all-in-one checklist above all the sections so I can quickly view what is done and what is not done.

### Prompt 6

As you can see, there are many files in the workspace which we created temporarily. Some of those are really valuable, but some of them can be deleted. Based on the current Git, let's go through and decide what needs to be moved, what needs to be deleted, what needs to be changed, and what is out of scope currently. Make the workspace back to a clean state before implementing anything else new

### Prompt 7

Okay, wish you can move the code base architecture analysis.md into the docs folder and then commit them all at once. You should revise the commit message.
- Move the code base architecture.md.
- Maybe implementation plan can go into the docs too.
- You can remove the HTML, and implementation plan.md can go into the docs too.
- Implementation plan is not a doc, right? It's not persistent documentation.
- Maybe code base analysis is going to the docs.
- Implementation plan.md, leave it.
- Impleme...

### Prompt 8

Approved


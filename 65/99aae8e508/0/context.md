# Session Context

## User Prompts

### Prompt 1

Based on the implementation plan.md, give us what we are working on and what we can continue. Start implementing the first task right now.

### Prompt 2

I think that's only a prototype, and the schedule JSON should be changed because I want separation of concerns. The schedule JSON should only be changed if we change the schedule, not the delivery. I think it will quickly explode the schedule JSON, and I wish we can save it somewhere else

### Prompt 3

This is where the run_once function lives, right? This is our core logic, right? I'm a little bit confused about the collector logic. The Ezoic, I think Ezoic content source or something, because I thought you are trying to import this into the content source itself

### Prompt 4

I thought send email was taking individual participants, sorry, recipients, so maybe there's still no need to change it. If send email takes one recipient at a time, then we should make it into run once, because which participant to send this question to is resolved there

### Prompt 5

Wait, I thought send email takes in one participant at a time. Is it, or does it take them a list? I want to get it clear right now

### Prompt 6

Maybe you can look into the architectural document and find whether we have this decision or not.

Currently, when I look into this decision, I think that we were trying to do a separation of concern because run once means the workflow. Run once didn't run once for all participants, right? It ran once, literally once, and I think that's our design. Send email will literally send all emails. Maybe we should keep that separation of concern. Now which participant gets sent is determined inside the ...

### Prompt 7

Proceed


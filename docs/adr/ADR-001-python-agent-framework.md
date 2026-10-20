# ADR-001: Python with Microsoft Agent Framework

Decision: all services in Python 3.11+; agents built with `agent-framework` (1.22+) and
`agent-framework-foundry`, hosted on Microsoft Foundry; front end in React + TypeScript.
Why: fastest path for a one-week build; the Agent Framework Python SDK covers agents, workflows
(sequential/concurrent/handoff), and OpenTelemetry out of the box; the team has Python depth.
Consequences: a .NET port is out of scope; enterprise shops on .NET can consume the API and schemas.

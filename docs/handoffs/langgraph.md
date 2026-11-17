# Tasks app: what Conductor needs to know

Written Nov 14, 2026 from the tasks app's design (`tasking/docs/`). For Conductor's architect and owner. It covers roadmap Phase 12 (the tasks and calendar domain) and one new piece of work: Discord as a third place to approve. Nothing here changes Conductor until its own phases are specified.

## Summary

The tasks app is the Python package `docket` in the `tasking` project. Phase 0 is specified and nothing is built yet. It gives Conductor an MCP server over stdio: read tools, plus write tools that run only after you approve the step in Conductor. Approving in Conductor is final; the tasks app never asks again.

## Decisions that affect Conductor

| Decision | What it means here |
| --- | --- |
| Conductor's approval is final (Nov 14) | The tasks app's write tools are Conductor `write` actions, not `propose`. An approved `create_task` creates the task at once, with no second card |
| No tool approves a proposal | Proposals (from cameras, later) are decided only by your press or command in the tasks app. Conductor can list them but never approve one |
| Approval places (Nov 14) | Conductor approvals and escalation answers in three places: the terminal, the 127.0.0.1 page, and Discord, all recorded in `conductor.db` through `conductor.decisions`. Discord matters most when you're away from the Mac; this may change if private routing to the Mac is set up |
| A shared Discord service (Nov 14) | A new project owns the bot token and the Gateway connection, posts cards for every app, and forwards presses to each app on 127.0.0.1. Conductor's Discord approvals go through it; Conductor runs no bot of its own |
| Tasks and calendar are one domain | Calendar reads (`list_events`, `check_availability`) are tools of the same `docket mcp serve` server, not a separate calendar server |
| Port | The tasks app's API is on 8767, next to Conductor's 8766. Conductor doesn't call the API; it uses stdio MCP |

## The MCP server

`docket mcp serve`, launched by Conductor as a child process (`CONDUCTOR_MCP__TASKS`, by Conductor's naming). Built in the tasks app's stage 6.

| Tool | Effect in Conductor | Notes |
| --- | --- | --- |
| `list_tasks(status)` | read | open, in progress, due, overdue, done, cancelled; capped with paging |
| `get_task(id)` | read | With reminder history and the linked events |
| `list_proposals` | read | Pending proposals with their source and evidence |
| `list_events(range)` | read | Every connected calendar (Google, iCloud, Outlook); a failing backend is named, never silently left out |
| `check_availability(range)` | read | Free and busy across every calendar |
| `create_task(title, deadline, request_key)` | write | Source `agent` |
| `change_deadline(id, deadline, request_key)` | write | |
| `plan_work_time(id, start, minutes, request_key)` | write | One planned time to work on a task, on one day; pick it with `check_availability` first |
| `snooze_task(id, minutes, request_key)` | write | Moves the next reminder only |
| `complete_task(id, request_key)` | write | Same path as the Done button |
| `cancel_task(id, request_key)` | write | |

- Read tools carry `readOnlyHint: true`, and every tool declares an output schema, as Conductor's tool check (Phase 6b) requires.
- Results are plain data: ISO times, ids and titles. Refusals are constant codes (`unknown_task`, `already_done`, `invalid_deadline`), never your input echoed back.
- **Deadlines** are sent as `date`, `time` (or null) and `time_zone`, as the email service sends them. A date with no time becomes 17:00 in that zone. A deadline is a fixed instant and doesn't move when you travel.
- **Titles are untrusted.** Many come from emails. They're plain text of at most 100 characters, and the planner and answer prompts treat them as data, never as instructions.
- **Calendar results carry other events' titles and times.** They stay on the machine, as finance results do, because Conductor runs on a local model.

## Work this means for Conductor

1. **Phase 12, the tasks domain.** The five reads become `read` actions and the six writes become `write` actions, with argument bounds tighter than the server's own, as the finance domain does. It also needs keyword rules (task, tasks, remind, deadline, due, calendar, schedule, free time), a fake server checked against a saved copy of the real schemas, and evaluation cases.
2. **`request_key`, filled by code.** Each write tool takes a `request_key` so that a step retried after a `timeout` or `closed` outcome can't create or change a task twice. Conductor treats those outcomes as unknown and asks you before retrying; the key makes that retry safe. The key must be `<run id>:<step id>`, filled by Conductor's code, never chosen by the planner. Today `StepRunner.run(action, args)` receives neither id, and the tool check requires every field a tool requires to be in the action's contract, which the planner fills. Phase 12 has to decide how an action declares a field that code fills in. For example:
   - the action marks `request_key` as code-filled, so it is left out of the planner's schema and added by `McpRunner` from the run and step;
   - or the runner adds it to every `write` call of a domain that asks for it.
3. **Discord as a third place to approve.** This needs the shared Discord service first. Conductor posts each `ApprovalRequest` and `Escalation` there as a card: the summary, the exact arguments, and Approve, Reject, Retry and Cancel buttons. Edits stay in the terminal or on the page. A press reaches `conductor.decisions` like the other two channels, so "first decision wins" and the stale-steps digest work unchanged. Every press is checked against your Discord user id. The design is Conductor's to write once the shared service's contract exists.
4. **Backlog item "a notification when an approval is waiting".** The Discord card in item 3 covers it.

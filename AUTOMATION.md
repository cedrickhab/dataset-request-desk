# Continuous execution versus cron
The user requested an automation PROMPT for a local coding agent. This pack does not activate a ChatGPT reminder or claim scheduled ChatGPT runs can manipulate a Windows repository. Start with one agent session using AGENT_PROMPT.md; its instruction to continue is often sufficient.
A cron trigger does not itself read docs, code, test or commit. It launches an already-installed agent CLI that has repository access and persisted progress. Exact CLI invocation depends on your agent; do not guess nonexistent flags. Configure its documented noninteractive mode and permissions yourself. No secret credentials in prompt arguments or logs.

## Optional WSL/Linux periodic resumption
Use a launcher you implement during scaffold: scripts/run-agent.sh. It obtains a nonblocking flock at a local ignored state path, exits if done, invokes your configured agent with AGENT_PROMPT.md, retains the lock for the ENTIRE invocation, and records exit status. The launched process must not detach. No parallel runs, no “stale” lock removal while a process lives. Agent itself validates evidence before continuing. Retry external launch errors with bounded backoff, not repeated commits. Store progress durably in repo; logs outside tracked files.
Example cron trigger every15minutes (install ONLY after launcher works):
*/15 * * * * /home/YOUR_USER/projects/dataset-request-desk/scripts/run-agent.sh >> /home/YOUR_USER/projects/dataset-request-desk/.agent-runs/runner.log 2>&1
Replace absolute paths; create log directory beforehand. Never paste placeholders unchanged. Host must be awake and Docker/agent available. Windows Task Scheduler can launch WSL equivalent, configured by user. The .agent-runs lock/log path is ignored. Completion stops launches via PROGRESS.json overall_status completed; remove/disable schedule too.

## Repeated-run prompt
Read AGENT_PROMPT.md and PROGRESS.json. Acquire the repository lock. If completed, exit without editing or committing. Otherwise validate saved evidence, resume the first unfinished numbered implementation task, finish its gate and continue to the next automatically. Test before each push, observe exact-SHA CI, preserve unrelated edits, write progress on interruption. Do not run deployment task12. Record genuine blockers without inventing success. Release lock on exit.

No schedule frequency was explicitly requested;15minutes is an editable example, not a schedule secretly activated. Cron is optional execution infrastructure, not the selected application background-job feature.

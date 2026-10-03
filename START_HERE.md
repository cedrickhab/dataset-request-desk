# Dataset Request Desk implementation pack
This is a specification and execution plan, not an implemented or tested application. The original candidate materials are included under reference/ and seed/. Read this file, AGENT_PROMPT.md, and docs/00_REQUIREMENTS.md before implementation. Work through docs/01 to docs/12 in order. Update PROGRESS.json after verified milestones. Do not deploy during the implementation sequence.

## Before starting on Cedrick's Windows computer
Use VS Code; IntelliJ is not needed for this Python project. Install Git and Docker Desktop with its WSL2 backend. Verify virtualization and Docker's current Windows requirements against the official installation guide. If your Windows version cannot run Docker Desktop, use a supported Linux environment rather than pretending Docker is working. Inside WSL Ubuntu, keep the repository under ~/projects rather than mixing Windows and Linux dependency directories. Use VS Code's WSL extension to open it.
Install a coding agent with terminal/file access and authenticate it yourself. For host development install Python 3.12 and Node.js 22; container-only execution can install runtimes inside images instead. Use VS Code Python and ESLint extensions. PostgreSQL runs in Docker; a second local database installation is unnecessary. A GitHub account and working authentication are needed. Claude is authorized to create the public repository and configure origin as described in CLAUDE_START_PROMPT.md. GitHub CLI is optional but useful for checking CI. No SendGrid, OTP provider, video storage, or cloud hosting account is needed now.

Check: git --version; docker --version; docker compose version; docker info. Check python --version and node --version if using host runtimes. These are checks, not an instruction to paste all commands into one shell line.

## Decisions
Django REST Framework + PostgreSQL + React/TypeScript/Vite. Django sessions with HttpOnly cookies and CSRF protection, no browser localStorage tokens. One origin through a proxy. No OTP or two-factor authentication, following the last user instruction. CI is included. Select the background export simulation as the ONE stretch item. Deployment is deferred; docs/12 is a later runbook, not authorization to provision resources. No real videos or downloads.
Extra local administrator: cedrichub85@gmail.com, from the spoken email. Verify its spelling locally before seeding. Set PERSONAL_ADMIN_PASSWORD in an ignored .env. Use a unique password from a password manager, at least 16 characters. No fixed personal password is included in this ZIP or Git. Supplied demo accounts remain unchanged for reviewer access.

## Execution
Copy this pack into an empty project directory. Read AGENT_PROMPT.md or paste it into the local agent. Use CLAUDE_START_PROMPT.md to create the remote through your authenticated GitHub session. The agent implements features, not merely documents, and proceeds automatically after passing each gate. The planning pack itself contains no actual implementation commits or pushes.
A long-running agent session is preferred. A cron schedule is only a trigger; use AUTOMATION.md if periodic resumption is needed. No ChatGPT scheduled automation has been activated by this pack.

## Time budget
The original brief asks for 6–8 hours, no more than about 10, due Sunday 4 October 2026 23:59 Africa/Kigali. Track actual focused time. Build required behavior before the stretch task. Do not consume the budget polishing the prototype or adding more optional features. If the budget is exhausted, preserve a working core and honestly list omissions.

## Updated prototype
Open prototype/index.html directly in Chrome. Demo-account buttons below the login fields fill credentials, then click Sign in. All roles have navigable workflows, with local browser persistence and reset. Read prototype/README.md for what is simulated. This white/amber version supersedes the earlier dark concept.

## Claude handoff
Read CLAUDE_GUIDE.md and paste CLAUDE_START_PROMPT.md into Claude Code in this folder. It includes public GitHub repository creation under cedrickhab with account defaults.

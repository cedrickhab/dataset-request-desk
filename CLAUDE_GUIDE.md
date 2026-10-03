# Working with Claude
1. Extract this ZIP into your project folder. Open that folder in VS Code.
2. Open prototype/index.html in your browser and explore it. It defines the approved layout.
3. Start Claude Code in the same folder using the tool you already installed. Sign in through its own supported flow. Do not paste passwords/tokens into the prompt.
4. Ensure Docker is running and Git is available. GitHub CLI is useful: run gh auth login yourself if needed, then gh auth status. The signed-in GitHub user must be cedrickhab.
5. Paste CLAUDE_START_PROMPT.md. It incorporates the repository creation and updated theme instructions and refers to the included numbered guides. No original task re-upload required.
6. Claude should implement and verify sequentially without asking to continue. Review the commands it executes. If interrupted, paste: “Read PROGRESS.json, validate actual files and resume AGENT_PROMPT.md from the first unfinished task. Keep the approved black/blue prototype layout.”
7. Explore real app with seed accounts and review code before submitting. Credentials shown in prototype are DEMO ONLY. Your real personal admin password comes from ignored env.

No repository has been created by this ZIP. The prompt authorizes Claude in your authenticated local session to create the public repository. No schedule, CI execution or cloud deployment has been performed here. GitHub account default branch is preserved; feature work branch may differ without changing repository defaults.

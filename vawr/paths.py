"""Where everything lives. In a source checkout all working data sits under
work/; an installed copy uses ~/.vawr, and VAWR_HOME overrides both."""

import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# A source checkout (with the research task suite) keeps its data in work/;
# an installed copy uses ~/.vawr. VAWR_HOME overrides both.
_CHECKOUT = os.path.isdir(os.path.join(REPO, "tasks")) and os.path.isdir(os.path.join(REPO, "vawr"))
WORK = os.environ.get("VAWR_HOME") or (os.path.join(REPO, "work") if _CHECKOUT
                                       else os.path.expanduser("~/.vawr"))
# where checking calls to `claude -p` run from
CHECK_CWD = REPO if _CHECKOUT else WORK
LOG_PATH = os.path.join(WORK, "log", "events.jsonl")
TASK_SRC = os.path.join(REPO, "tasks")            # tracked task definitions
TASK_REPO = os.path.join(WORK, "task-repo")       # git repo built from TASK_SRC
RUNS_DIR = os.path.join(WORK, "runs")             # one git worktree per run
MANIFESTS = os.path.join(WORK, "manifests")       # one JSON file per run
ENV_FILE = os.path.join(REPO, ".env")
# Claude Code keeps session files under its config folder, which CLAUDE_CONFIG_DIR moves
CLAUDE_PROJECTS = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")


def project_dir_name(path):
    """Claude Code's folder name for a working directory: every character that
    isn't a letter or digit becomes '-'."""
    return "".join(c if c.isalnum() else "-" for c in os.path.abspath(path))

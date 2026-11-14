"""Where everything lives. All working data sits under work/, which git ignores."""

import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(REPO, "work")
LOG_PATH = os.path.join(WORK, "log", "events.jsonl")
TASK_SRC = os.path.join(REPO, "tasks")            # tracked task definitions
TASK_REPO = os.path.join(WORK, "task-repo")       # git repo built from TASK_SRC
RUNS_DIR = os.path.join(WORK, "runs")             # one git worktree per run
MANIFESTS = os.path.join(WORK, "manifests")       # one JSON file per run
ENV_FILE = os.path.join(REPO, ".env")
CLAUDE_PROJECTS = os.path.expanduser("~/.claude/projects")


def project_dir_name(path):
    """Claude Code's folder name for a working directory: every character that
    isn't a letter or digit becomes '-'."""
    return "".join(c if c.isalnum() else "-" for c in os.path.abspath(path))

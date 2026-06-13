# Deployment — Installing Ralph on a New Machine

> From zero to `ralph init` on a brand-new system.

---

## Prerequisites

Before installing Ralph, ensure these are available:

| Tool | How to Check | How to Install |
|------|-------------|----------------|
| **git** | `git --version` | `brew install git` (macOS) or `apt install git` (Linux) |
| **Python 3.10+** | `python3 --version` | `brew install python@3.12` or [python.org](https://www.python.org/downloads/) |
| **beads (bd)** | `bd --version` | [beads docs](https://github.com/beadsboard/beads) |
| **kimi or pi** | `which kimi` or `which pi` | At least one AI agent CLI |
| **GitHub access** | `git ls-remote https://github.com/samdharma/Ralph_loop.git HEAD` | Required for clone and push |

---

## Step-by-Step Installation

```mermaid
graph LR
    A[Install<br/>Prerequisites] --> B[Clone Ralph<br/>to ~/.ralph]
    B --> C[Run install.sh]
    C --> D[Source shell<br/>profile]
    D --> E[Verify<br/>ralph version]
    E --> F[ralph init]
</```

### Step 1: Install Prerequisites

```bash
# macOS (Homebrew)
brew install git python@3.12

# Verify
git --version
python3 --version
```

Install beads and your AI agent following their respective documentation.

### Step 2: Clone Ralph

```bash
git clone https://github.com/samdharma/Ralph_loop.git ~/.ralph
```

### Step 3: Run the Installer

```bash
bash ~/.ralph/scripts/install.sh
```

The installer:
1. Symlinks `~/.ralph/bin/ralph` to `/usr/local/bin/ralph` (or `~/.local/bin/ralph`)
2. Sets execute permissions on all Ralph scripts
3. Adds `RALPH_HOME` to your shell profile

### Step 4: Source Your Profile

```bash
source ~/.zshrc    # or source ~/.bashrc
```

### Step 5: Verify Installation

```bash
ralph version      # → ralph v1.2.0
ralph help         # show all commands
echo $RALPH_HOME   # → /Users/you/.ralph
```

### Step 6: Initialize Your First Project

```bash
ralph init
```

Answer the prompts and Ralph scaffolds a complete project with git, beads, config files, templates, and test directories.

---

## Post-Install: What Ralph Needs

| Requirement | Created by `ralph init`? | Notes |
|-------------|--------------------------|-------|
| Git repo | yes | `git init` |
| Beads initialized | yes | `bd init` |
| `.ralph/config.toml` | yes | single source of truth |
| `docs/agent/PROMPT.md` | yes | rendered from template |
| `config/ralph_preflight.sh` | yes | default: skips epics/features |
| `docs/agent/prompts/sessions/` | yes | 4-session pipeline prompts |
| `.gitignore` | yes | ralph runtime exclusions |
| AI agent in PATH | **no** — install separately | `which kimi` or `which pi` |
| GitHub remote | **no** — set up manually | `git remote add origin <url>` |

---

## Checking if Ralph is Installed

```bash
# Fastest check
ralph version

# Full verification
which ralph && ralph version && echo "RALPH_HOME=$RALPH_HOME"

# Troubleshoot missing ralph command
ls -la ~/.ralph/bin/ralph          # is the repo cloned?
ls -la /usr/local/bin/ralph        # is the symlink there?
ls -la ~/.local/bin/ralph          # alternative symlink location
echo $PATH | tr ':' '\n'           # is the bin directory on PATH?
```

---

## Updating Ralph

```bash
cd ~/.ralph
git pull
bash scripts/install.sh     # update symlinks if needed
```

---

## Uninstalling

```bash
rm -f /usr/local/bin/ralph ~/.local/bin/ralph
rm -rf ~/.ralph
# Edit ~/.zshrc or ~/.bashrc and remove RALPH_HOME lines
```

---

## Deployment Checklist

- [ ] git installed (`git --version`)
- [ ] Python 3.10+ installed (`python3 --version`)
- [ ] beads installed (`bd --version`)
- [ ] At least one AI agent installed (`which kimi` or `which pi`)
- [ ] GitHub access verified
- [ ] Ralph cloned to `~/.ralph`
- [ ] `install.sh` run successfully
- [ ] `ralph version` works from any directory
- [ ] `RALPH_HOME` set in shell profile
- [ ] First project initialized with `ralph init`

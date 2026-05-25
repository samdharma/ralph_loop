#!/usr/bin/env python3
"""
Ralph Wiggum Loop Build System — Project Initializer

Interactive Q&A wizard that scaffolds a new project with:
- Git + Beads initialized
- Ralph core scripts copied into scripts/ralph/
- All templates rendered with user's answers
- Language-specific validation gate configured

Usage:
    ralph init                  # Interactive mode
    python3 init.py             # Direct invocation
    python3 init.py --status    # Show project health dashboard
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────
RALPH_HOME = Path(os.environ.get("RALPH_HOME", Path(__file__).parent.resolve()))
RALPH_VERSION = "1.0.0"
CORE_DIR = RALPH_HOME / "core"
TEMPLATES_DIR = RALPH_HOME / "templates"

BANNER = r"""
  ██████╗  █████╗ ██╗     ██████╗ ██╗  ██╗
  ██╔══██╗██╔══██╗██║     ██╔══██╗██║  ██║
  ██████╔╝███████║██║     ██████╔╝███████║
  ██╔══██╗██╔══██║██║     ██╔═══╝ ██╔══██║
  ██║  ██║██║  ██║███████╗██║     ██║  ██║
  ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝  ╚═╝

  Ralph Wiggum Loop Build System — Project Initializer
"""

# ──────────────────────────────────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────────────────────────────────

def green(text: str) -> str:
    return f"\033[0;32m{text}\033[0m"

def yellow(text: str) -> str:
    return f"\033[1;33m{text}\033[0m"

def red(text: str) -> str:
    return f"\033[0;31m{text}\033[0m"

def bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"

def checkmark() -> str:
    return green("✓")


def slugify(name: str) -> str:
    """Convert a project name to a kebab-case slug."""
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


def package_name(name: str) -> str:
    """Convert a project name to a Python-safe package name (snake_case)."""
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9]+', '_', name)
    name = name.strip('_')
    # Must start with a letter or underscore
    if name and name[0].isdigit():
        name = '_' + name
    return name


def which(cmd: str) -> Optional[str]:
    """Check if a command is in PATH."""
    result = shutil.which(cmd)
    return result


def run(cmd: list[str], cwd: Optional[Path] = None, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    kwargs = {}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    if cwd:
        kwargs["cwd"] = str(cwd)
    return subprocess.run(cmd, **kwargs)


def check_prerequisites() -> list[str]:
    """Return list of missing prerequisites."""
    missing = []

    if not which("git"):
        missing.append("git — https://git-scm.com/downloads")

    if not which("bd"):
        missing.append("beads (bd) — https://github.com/beadsboard/beads")

    if not which("python3"):
        missing.append("python3 — https://www.python.org/downloads/")

    py_version = sys.version_info
    if py_version.major < 3 or (py_version.major == 3 and py_version.minor < 10):
        missing.append("python 3.10+ (current: {}.{})".format(py_version.major, py_version.minor))

    # At least one agent must be available
    has_kimi = which("kimi") is not None
    has_pi = which("pi") is not None
    if not has_kimi and not has_pi:
        missing.append("kimi or pi — at least one AI agent CLI is required")

    return missing


def detect_available_agents() -> dict[str, str]:
    """Return dict of {name: path} for available agents."""
    agents = {}
    if which("kimi"):
        agents["kimi"] = "Kimi CLI"
    if which("pi"):
        agents["pi"] = "Pi Coding Agent"
    return agents


def render_template(template_path: Path, variables: dict[str, str]) -> str:
    """Simple {{ VAR }} template rendering. No Jinja2 dependency needed."""
    content = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        content = content.replace("{{ " + key + " }}", value)
        content = content.replace("{{" + key + "}}", value)
    return content


# ──────────────────────────────────────────────────────────────────────
# Language profiles
# ──────────────────────────────────────────────────────────────────────

LANGUAGE_PROFILES = {
    "python": {
        "name": "Python",
        "test_framework": "pytest",
        "test_dir": "tests",
        "test_command_unit": "pytest tests/unit/ -q --tb=short",
        "test_command_smoke": "pytest tests/unit/ -x -q --tb=short -m unit",
        "test_command_integration": "pytest tests/integration/ -q --tb=short -m integration",
        "test_command_full": "pytest tests/ -q --tb=short -m 'not e2e and not performance'",
        "lint_tools": "black isort flake8 mypy",
        "lint_conventions": "Type hints on all public APIs. Ruff + Black.",
        "source_dir": "src",
        "init_commands": [],
    },
    "node": {
        "name": "Node.js / TypeScript",
        "test_framework": "jest",
        "test_dir": "__tests__",
        "test_command_unit": "npx jest --testPathPattern='__tests__/unit/' --verbose",
        "test_command_smoke": "npx jest --testPathPattern='__tests__/unit/' --bail",
        "test_command_integration": "npx jest --testPathPattern='__tests__/integration/'",
        "test_command_full": "npx jest --testPathPattern='__tests__/'",
        "lint_tools": "eslint prettier",
        "lint_conventions": "ESLint + Prettier. TypeScript strict mode.",
        "source_dir": "src",
        "init_commands": [],
    },
    "go": {
        "name": "Go",
        "test_framework": "go test",
        "test_dir": "test",
        "test_command_unit": "go test ./... -short",
        "test_command_smoke": "go test ./... -short -count=1",
        "test_command_integration": "go test ./... -run Integration",
        "test_command_full": "go test ./... -count=1",
        "lint_tools": "golangci-lint gofmt",
        "lint_conventions": "golangci-lint + gofmt. Standard Go project layout.",
        "source_dir": "",
        "init_commands": ["go mod init {{ PROJECT_SLUG }}"],
    },
    "rust": {
        "name": "Rust",
        "test_framework": "cargo test",
        "test_dir": "tests",
        "test_command_unit": "cargo test --lib",
        "test_command_smoke": "cargo test --lib -- --test-threads=1",
        "test_command_integration": "cargo test --test '*'",
        "test_command_full": "cargo test",
        "lint_tools": "clippy rustfmt",
        "lint_conventions": "Clippy + rustfmt. Edition 2021.",
        "source_dir": "src",
        "init_commands": ["cargo init --name {{ PROJECT_SLUG }}"],
    },
    "other": {
        "name": "Other / Custom",
        "test_framework": "custom",
        "test_dir": "tests",
        "test_command_unit": "# TODO: add your test command",
        "test_command_smoke": "# TODO: add your smoke test command",
        "test_command_integration": "# TODO: add your integration test command",
        "test_command_full": "# TODO: add your full test command",
        "lint_tools": "custom",
        "lint_conventions": "Define your own conventions.",
        "source_dir": "src",
        "init_commands": [],
    },
}


# ──────────────────────────────────────────────────────────────────────
# Interactive Wizard
# ──────────────────────────────────────────────────────────────────────

def wizard() -> dict[str, str]:
    """Run the interactive Q&A and return the variables dict."""
    print(BANNER)
    print()

    # --- Prerequisites ---
    missing = check_prerequisites()
    if missing:
        print(f"{red('Missing prerequisites:')}")
        for m in missing:
            print(f"  {red('✗')} {m}")
        print()
        print("Install the above and run 'ralph init' again.")
        sys.exit(1)

    # --- Project Name ---
    print(f"{bold('Project name')}: ", end="")
    project_name = input().strip()
    while not project_name:
        print(f"  {yellow('Project name is required.')}")
        print(f"{bold('Project name')}: ", end="")
        project_name = input().strip()

    project_slug = slugify(project_name)
    project_package = package_name(project_name)

    # --- Project Directory ---
    default_dir = str(Path.cwd() / project_slug)
    print(f"{bold('Project directory')} [{default_dir}]: ", end="")
    project_dir_input = input().strip()
    project_dir = Path(project_dir_input) if project_dir_input else Path(default_dir)

    # --- Language ---
    print(f"{bold('Primary language')} [python]:")
    langs = list(LANGUAGE_PROFILES.keys())
    for i, lang in enumerate(langs, 1):
        marker = " (default)" if lang == "python" else ""
        print(f"  {i}) {lang} — {LANGUAGE_PROFILES[lang]['name']}{marker}")
    print(f"{bold('Choose')} [1]: ", end="")
    lang_choice = input().strip()
    if lang_choice and lang_choice.isdigit():
        idx = int(lang_choice) - 1
        language = langs[idx] if 0 <= idx < len(langs) else "python"
    else:
        language = "python"

    profile = LANGUAGE_PROFILES[language]

    # --- AI Agent ---
    agents = detect_available_agents()
    print(f"{bold('AI agent')}:")
    agent_list = list(agents.keys())
    agent_list.append("both")
    agent_list.append("auto")
    for i, ag in enumerate(agent_list, 1):
        if ag == "both":
            label = "both — Try kimi, fall back to pi"
        elif ag == "auto":
            label = "auto — Detect best available"
        else:
            label = f"{ag} — {agents[ag]} {'(available)' if ag in agents else '(not installed)'}"
        print(f"  {i}) {label}")
    default_agent = agent_list.index("both") + 1
    if "kimi" in agents and "pi" not in agents:
        default_agent = agent_list.index("kimi") + 1
    elif "pi" in agents and "kimi" not in agents:
        default_agent = agent_list.index("pi") + 1
    print(f"{bold('Choose')} [{default_agent}]: ", end="")
    agent_choice = input().strip()
    if agent_choice and agent_choice.isdigit():
        idx = int(agent_choice) - 1
        agent_cmd = agent_list[idx] if 0 <= idx < len(agent_list) else "both"
    else:
        agent_cmd = agent_list[default_agent - 1]

    # --- Test Framework ---
    default_test = profile["test_framework"]
    print(f"{bold('Test framework')} [{default_test}]: ", end="")
    test_framework = input().strip() or default_test

    # Test commands based on framework
    if test_framework != profile["test_framework"]:
        # User overrode — use sensible defaults
        tc_unit = f"# TODO: add your unit test command using {test_framework}"
        tc_smoke = f"# TODO: add your smoke test command using {test_framework}"
        tc_integration = f"# TODO: add your integration test command using {test_framework}"
        tc_full = f"# TODO: add your full test command using {test_framework}"
    else:
        tc_unit = profile["test_command_unit"]
        tc_smoke = profile["test_command_smoke"]
        tc_integration = profile["test_command_integration"]
        tc_full = profile["test_command_full"]

    # --- Lint Tools ---
    default_lint = profile["lint_tools"]
    print(f"{bold('Lint / format tools')} [{default_lint}]: ", end="")
    lint_tools = input().strip() or default_lint

    # --- Description ---
    print(f"{bold('Brief project description')}:")
    print("  > ", end="")
    description = input().strip()
    if not description:
        description = f"A {language} project."

    # --- Test directory ---
    default_test_dir = profile["test_dir"]
    print(f"{bold('Test directory')} [{default_test_dir}]: ", end="")
    test_dir = input().strip() or default_test_dir

    # --- Source directory ---
    default_src = profile["source_dir"]
    src_dir_prompt = f"{bold('Source directory')} [{default_src}]: " if default_src else f"{bold('Source directory')} [.] : "
    print(src_dir_prompt, end="")
    source_dir = input().strip() or default_src

    # --- Summary ---
    print()
    print(f"  {bold('Summary:')}")
    print(f"    Project:       {project_name}")
    print(f"    Directory:     {project_dir}")
    print(f"    Package:       {project_package}")
    print(f"    Language:      {language}")
    print(f"    AI Agent:      {agent_cmd}")
    print(f"    Test runner:   {test_framework}")
    print(f"    Lint tools:    {lint_tools}")
    print(f"    Description:   {description}")
    print()
    print(f"{bold('Proceed?')} [Y/n]: ", end="")
    confirm = input().strip().lower()
    if confirm and confirm not in ("y", "yes", ""):
        print("Aborted.")
        sys.exit(0)

    return {
        "PROJECT_NAME": project_name,
        "PROJECT_SLUG": project_slug,
        "PROJECT_PACKAGE": project_package,
        "PROJECT_DIR": str(project_dir),
        "PROJECT_DESCRIPTION": description,
        "PROJECT_LANGUAGE": language,
        "PROJECT_ROOT": str(project_dir.resolve()),
        "AGENT_CMD": agent_cmd,
        "TEST_FRAMEWORK": test_framework,
        "TEST_DIR": test_dir,
        "SOURCE_DIR": source_dir,
        "LINT_TOOLS": lint_tools,
        "LINT_CONVENTIONS": profile["lint_conventions"],
        "TEST_COMMAND_UNIT": tc_unit,
        "TEST_COMMAND_SMOKE": tc_smoke,
        "TEST_COMMAND_INTEGRATION": tc_integration,
        "TEST_COMMAND_FULL": tc_full,
        "RALPH_VERSION": RALPH_VERSION,
        "INIT_DATE": date.today().isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────
# Scaffolder
# ──────────────────────────────────────────────────────────────────────

def scaffold(vars: dict[str, str]) -> None:
    """Create the project from templates."""
    project_dir = Path(vars["PROJECT_DIR"])

    # --- Create directories ---
    print()
    dirs_to_create = [
        project_dir,
        project_dir / "scripts" / "ralph",
        project_dir / "config",
        project_dir / "docs" / "agent" / "prompts",
        project_dir / "logs",
        project_dir / vars["TEST_DIR"] / "unit",
        project_dir / vars["TEST_DIR"] / "integration",
    ]
    if vars["SOURCE_DIR"] and vars["SOURCE_DIR"] != ".":
        if vars["PROJECT_LANGUAGE"] == "python":
            dirs_to_create.append(project_dir / vars["SOURCE_DIR"] / vars["PROJECT_PACKAGE"])
        else:
            dirs_to_create.append(project_dir / vars["SOURCE_DIR"])

    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    print(f"  {checkmark()} Created project directory")

    # --- Git init ---
    if not (project_dir / ".git").exists():
        run(["git", "init"], cwd=project_dir)
        print(f"  {checkmark()} Initialized git repository")
    else:
        print(f"  {checkmark()} Git repository already exists")

    # --- Beads init ---
    if not (project_dir / ".beads").exists():
        result = run(["bd", "init"], cwd=project_dir)
        if result.returncode == 0:
            print(f"  {checkmark()} Initialized beads (bd init)")
        else:
            print(f"  {yellow('⚠')}  Beads init may have failed — run 'bd init' manually")
    else:
        print(f"  {checkmark()} Beads already initialized")

    # --- Run language-specific init commands ---
    profile = LANGUAGE_PROFILES.get(vars["PROJECT_LANGUAGE"], LANGUAGE_PROFILES["other"])
    for cmd_template in profile["init_commands"]:
        cmd_str = render_template_str(cmd_template, vars)
        print(f"  → Running: {cmd_str}")
        run(cmd_str.split(), cwd=project_dir)

    # --- Copy core scripts ---
    core_dest = project_dir / "scripts" / "ralph"
    core_scripts = [
        "ralph_loop.sh",
        "run_ralph_loop.sh",
        "ralph_preflight.sh",
        "ralph_validate.sh",
        "ralph_health.sh",
        "ralph_metrics.sh",
        "ralph_metrics_viewer.py",
        "ralph_report.sh",
        "ralph_report.py",
        "ralph_check_specs.py",
        "ralph_performance_check.sh",
        "detect_affected_tests.py",
    ]

    for script in core_scripts:
        src = CORE_DIR / script
        dst = core_dest / script
        if src.exists():
            shutil.copy2(src, dst)
            # Ensure executable for shell scripts
            if script.endswith(".sh"):
                dst.chmod(dst.stat().st_mode | 0o111)

    print(f"  {checkmark()} Installed Ralph core scripts → scripts/ralph/")

    # --- Render and write templates ---
    template_files = {
        TEMPLATES_DIR / "AGENTS.md.j2": project_dir / "AGENTS.md",
        TEMPLATES_DIR / "PROMPT.md.j2": project_dir / "docs" / "agent" / "PROMPT.md",
        TEMPLATES_DIR / "PROGRESS.md.j2": project_dir / "docs" / "agent" / "PROGRESS.md",
        TEMPLATES_DIR / "ralph_preflight.sh.j2": project_dir / "config" / "ralph_preflight.sh",
        TEMPLATES_DIR / "TEST_MAP.yaml.j2": project_dir / "config" / "TEST_MAP.yaml",
        TEMPLATES_DIR / "gitignore.j2": project_dir / ".gitignore",
    }

    for template_path, dest_path in template_files.items():
        if template_path.exists():
            rendered = render_template(template_path, vars)
            dest_path.write_text(rendered, encoding="utf-8")
            if dest_path.name.endswith(".sh"):
                dest_path.chmod(0o755)

    # Copy prompt extensions
    prompts_src = TEMPLATES_DIR / "prompts"
    prompts_dst = project_dir / "docs" / "agent" / "prompts"
    if prompts_src.exists():
        for prompt_file in prompts_src.iterdir():
            if prompt_file.suffix == ".md":
                shutil.copy2(prompt_file, prompts_dst / prompt_file.name)

    print(f"  {checkmark()} Generated AGENTS.md")
    print(f"  {checkmark()} Generated docs/agent/PROMPT.md")
    print(f"  {checkmark()} Generated docs/agent/PROGRESS.md")
    print(f"  {checkmark()} Generated docs/agent/prompts/")
    print(f"  {checkmark()} Generated config/ralph_preflight.sh")
    print(f"  {checkmark()} Generated config/TEST_MAP.yaml")
    print(f"  {checkmark()} Generated .gitignore")

    # --- Make config preflight executable ---
    preflight_path = project_dir / "config" / "ralph_preflight.sh"
    if preflight_path.exists():
        preflight_path.chmod(0o755)

    # --- Create initial test placeholder ---
    unit_test_dir = project_dir / vars["TEST_DIR"] / "unit"
    init_py = unit_test_dir / "__init__.py"
    if vars["PROJECT_LANGUAGE"] == "python" and not init_py.exists():
        init_py.write_text("# Unit tests\n")
        (project_dir / vars["TEST_DIR"] / "__init__.py").write_text("# Tests\n")
        integration_dir = project_dir / vars["TEST_DIR"] / "integration"
        (integration_dir / "__init__.py").write_text("# Integration tests\n")

    # --- Create source placeholder ---
    if vars["SOURCE_DIR"] and vars["SOURCE_DIR"] != "." and vars["PROJECT_LANGUAGE"] == "python":
        src_init = project_dir / vars["SOURCE_DIR"] / vars["PROJECT_PACKAGE"] / "__init__.py"
        if not src_init.exists():
            src_init.parent.mkdir(parents=True, exist_ok=True)
            src_init.write_text(f"# {vars['PROJECT_NAME']}\n")

    print()
    print(f"  {green('✓ Project initialized!')}")
    print()
    print(f"  {bold('Quick start:')}")
    print(f"    cd {vars['PROJECT_DIR']}")
    print(f"    bash scripts/ralph/ralph_loop.sh --agent={vars['AGENT_CMD']}")
    print()
    print(f"  {bold('Next steps:')}")
    print(f"    1. Review and customize AGENTS.md")
    print(f"    2. Review docs/agent/PROMPT.md for project-specific context")
    print(f"    3. Create your first ticket: bd new \"My first task\"")
    print(f"    4. Start the loop: bash scripts/ralph/run_ralph_loop.sh")


def render_template_str(template: str, vars: dict[str, str]) -> str:
    """Render a template string."""
    result = template
    for key, value in vars.items():
        result = result.replace("{{ " + key + " }}", value)
        result = result.replace("{{" + key + "}}", value)
    return result


# ──────────────────────────────────────────────────────────────────────
# Status Dashboard
# ──────────────────────────────────────────────────────────────────────

def status_dashboard() -> None:
    """Show project health dashboard (ralph status command)."""
    project_dir = Path.cwd()

    # Check if this is a ralph-initialized project
    if not (project_dir / "scripts" / "ralph" / "ralph_loop.sh").exists():
        print(f"{red('Not a Ralph-initialized project.')}")
        print("Run 'ralph init' first.")
        sys.exit(1)

    # Detect agent
    if which("pi"):
        agent = "pi"
    elif which("kimi"):
        agent = "kimi"
    else:
        agent = "unknown"

    print()
    print(f"  {bold('Project:')} {project_dir.name}")
    print(f"  {bold('Ralph version:')} {RALPH_VERSION}")
    print()

    # Ralph Loop status
    print(f"  {bold('── Ralph Loop ──')}")
    checkpoint = project_dir / ".ralph_checkpoint.json"
    pidfile = project_dir / ".ralph_loop.pid"

    loop_status = "IDLE"
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)
            loop_status = f"RUNNING (PID {pid})"
        except (OSError, ValueError):
            loop_status = "STALE PID"

    print(f"  Status:        {loop_status}")
    if checkpoint.exists():
        mtime = checkpoint.stat().st_mtime
        import time
        age = int(time.time() - mtime)
        print(f"  Checkpoint:    {age}s old (active iteration)")
    else:
        print(f"  Checkpoint:    none (idle)")

    # Metrics
    metrics_file = project_dir / "logs" / "ralph_metrics.jsonl"
    if metrics_file.exists():
        try:
            import json
            iterations = 0
            passes = 0
            fails = 0
            today = date.today().isoformat()
            today_iters = 0
            with open(metrics_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                        if ev.get("event") == "iteration_end":
                            iterations += 1
                            if ev.get("timestamp", "").startswith(today):
                                today_iters += 1
                        if ev.get("event") == "checkpoint_cleared":
                            passes += 1
                        elif ev.get("event") == "checkpoint_retained":
                            fails += 1
                    except json.JSONDecodeError:
                        pass
            total = passes + fails
            pass_rate = (passes / total * 100) if total > 0 else 0
            print(f"  Iterations today: {today_iters}")
            print(f"  Total iterations: {iterations}")
            print(f"  Pass rate:     {pass_rate:.1f}% ({passes}/{total})")
        except Exception:
            print(f"  Metrics:       unable to parse")
    else:
        print(f"  Metrics:       no data yet")

    print()

    # Beads Queue
    print(f"  {bold('── Beads Queue ──')}")
    if (project_dir / ".beads").exists():
        result = run(["bd", "list", "--json"], cwd=project_dir)
        if result.returncode == 0 and result.stdout.strip():
            try:
                import json
                tickets = json.loads(result.stdout)
                if isinstance(tickets, list):
                    statuses = {}
                    for t in tickets:
                        s = t.get("status", "unknown")
                        statuses[s] = statuses.get(s, 0) + 1
                    for s, c in sorted(statuses.items()):
                        print(f"  {s.capitalize():12s}: {c}")
                else:
                    print(f"  (unable to parse queue)")
            except json.JSONDecodeError:
                print(f"  (unable to parse queue)")
        else:
            # Try bd ready for a simpler view
            result2 = run(["bd", "ready", "--json"], cwd=project_dir)
            if result2.returncode == 0 and result2.stdout.strip():
                try:
                    import json
                    ready = json.loads(result2.stdout)
                    if isinstance(ready, list):
                        print(f"  Ready:          {len(ready)}")
                except json.JSONDecodeError:
                    pass
            print(f"  (queue status unknown)")
    else:
        print(f"  No beads database found")
    print()

    # Git
    print(f"  {bold('── Git ──')}")
    if (project_dir / ".git").exists():
        # Branch
        result = run(["git", "branch", "--show-current"], cwd=project_dir)
        branch = result.stdout.strip() if result.returncode == 0 else "unknown"
        print(f"  Branch:        {branch}")

        # Dirty?
        result = run(["git", "status", "--porcelain"], cwd=project_dir)
        dirty = "yes" if result.stdout.strip() else "no"
        print(f"  Dirty:         {dirty}")

        # Ahead/behind
        result = run(["git", "rev-list", "--count", "HEAD..@{u}"], cwd=project_dir)
        ahead = result.stdout.strip() if result.returncode == 0 else "?"
        result = run(["git", "rev-list", "--count", "@{u}..HEAD"], cwd=project_dir)
        behind = result.stdout.strip() if result.returncode == 0 else "?"
        print(f"  Ahead/Behind:  +{behind}/-{ahead}")
    else:
        print(f"  Not a git repository")
    print()

    # Health
    print(f"  {bold('── Health ──')}")
    health_script = project_dir / "scripts" / "ralph" / "ralph_health.sh"
    if health_script.exists():
        result = run(["bash", str(health_script)], cwd=project_dir)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and not line.startswith("[CHECK]"):
                if "HEALTHY" in line:
                    print(f"  {checkmark()} {line}")
                elif "UNHEALTHY" in line:
                    print(f"  {red('✗')} {line}")
                elif line.startswith("  -"):
                    print(f"    {line}")
    print()


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main() -> int:
    if "--status" in sys.argv:
        status_dashboard()
        return 0

    vars = wizard()
    scaffold(vars)
    return 0


if __name__ == "__main__":
    sys.exit(main())

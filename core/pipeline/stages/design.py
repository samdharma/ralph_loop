"""DESIGN stage (C1 step 10 — per plan §1.1 C1).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the DESIGN stage lives
at ``core/pipeline/stages/design.py``. It runs the architect
sub-agent that reads the issue + codebase and writes the design
spec to ``docs/designs/<N>.md``.

Per spec §10.1 A3 (R1), the artifact-based handoff means the
DESIGN agent writes its outputs to the artifact directory
(``.ralph/issues/<N>/artifacts/``). The session-file write that
previously carried Mode-B context is now a no-op
(``--continue`` / ``--session`` are no longer used).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Bootstrap sys.path so core.engine and core.pipeline.stages.base can
# be imported when this module is loaded via pytest from a tests/
# subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.pipeline.stages.base import Stage  # noqa: E402

# PROJECT_ROOT is the directory containing ``.ralph/`` and ``docs/``.
# Tests override via monkeypatch.
PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
DESIGN_SPEC_DIR = PROJECT_ROOT / "docs" / "designs"


def _design_spec_path(issue_num: int) -> Path:
    """Return the canonical path of the design spec for ``issue_num``.

    Per spec §6.2: ``docs/designs/<N>.md`` (one file per issue).
    """
    return DESIGN_SPEC_DIR / f"{issue_num}.md"


def run_design_stage(issue: dict) -> bool:
    """STAGE 1: Architect persona — reads issue + codebase, writes design spec.

    The session-file write for Mode B is preserved as a no-op for
    API compatibility with the (removed) ``--continue`` mechanism.
    """
    issue_num = issue["number"]
    print(f"\n[ralph] STAGE 1/3: DESIGN for #{issue_num}")
    # Lazy import — gh_comment lives in core.pipeline.github.comments
    # (C1 step 4).
    from core.pipeline.github.comments import gh_comment

    gh_comment(issue_num, "🎨 DESIGN stage started.")
    # Lazy import — log_metrics lives at core.pipeline.retry.
    from core.pipeline.retry import log_metrics

    log_metrics("stage_start", issue=str(issue_num), stage="design")

    # Create the per-issue design spec placeholder BEFORE the agent runs,
    # so the agent sees the file exists and has a path to write to.
    design_file = _design_spec_path(issue_num)
    design_file.parent.mkdir(parents=True, exist_ok=True)
    if not design_file.exists():
        design_file.write_text(
            f"# Design Spec: #{issue_num} <title>\n\n"
            f"<!-- Engine-created placeholder. "
            f"The DESIGN agent will overwrite this file. -->\n",
            encoding="utf-8",
        )
        print(f"[ralph] Created placeholder {design_file}")

    session_file = PROJECT_ROOT / ".ralph" / f"session-{issue_num}.jsonl"
    # assemble_stage_prompt lives in core.pipeline.prompts.
    from core.pipeline.agents.pi import invoke_agent
    from core.pipeline.prompts import assemble_stage_prompt

    prompt = assemble_stage_prompt(issue, "design.md")
    success = invoke_agent(prompt, issue_num, session_file=session_file)

    if success:
        if not design_file.exists():
            print(f"[ralph] WARNING: DESIGN agent did not create {design_file}.")
        else:
            content = design_file.read_text(encoding="utf-8")
            if "<!-- Engine-created placeholder" in content:
                print(
                    f"[ralph] WARNING: DESIGN agent left placeholder {design_file} "
                    f"untouched. Design may not have been written."
                )
            else:
                print(f"[ralph] Design spec written to {design_file}")

    log_metrics("stage_complete", issue=str(issue_num), stage="design")
    return success


class DesignStage(Stage):
    """DESIGN pipeline stage — runs the architect sub-agent."""

    name = "design"

    def run(self, issue: dict, **kwargs: Any) -> bool:
        """Run the DESIGN stage. Delegates to :func:`run_design_stage`."""
        return run_design_stage(issue)


__all__ = ["DesignStage", "run_design_stage", "_design_spec_path"]  # noqa: D401

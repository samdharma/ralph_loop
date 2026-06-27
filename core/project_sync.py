#!/usr/bin/env python3
"""
Ralph v3 — GitHub Projects v2 Board Sync

Keeps the GitHub Project Kanban board in sync with Ralph's status labels.
Labels remain the source of truth; this module mirrors them to the Project's
"Status" field so the board is visually useful.

The sync is best-effort and fail-soft: if the project board cannot be updated,
Ralph logs a warning and continues. The pipeline must never break because of a
board sync failure.

Configuration in .ralph/config.toml:

    [ticket]
    repo = "owner/repo"
    project = 1                       # GitHub project number (optional)

    [project]
    status_field = "Status"           # default
    status_map = {                    # default mapping shown
        "status:ready"  = "Ready",
        "status:design" = "In Progress",
        "status:build"  = "In Progress",
        "status:verify" = "In Progress",
        "status:review" = "Review",
        "status:blocked"= "Blocked",
    }

Environment variables:
    RALPH_GITHUB_PROJECT    Override config project number.
    RALPH_PROJECT_SYNC      Set to "0" to disable board sync even when
                            ticket.project is configured; set to "1" to
                            enable it (default follows ticket.project).
    RALPH_PROJECT_DIR       Project root (default: cwd).
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
CONFIG_FILE = PROJECT_ROOT / ".ralph" / "config.toml"

DEFAULT_STATUS_MAP = {
    "status:ready": "Ready",
    "status:design": "In Progress",
    "status:build": "In Progress",
    "status:verify": "In Progress",
    "status:review": "Review",
    "status:blocked": "Blocked",
}

DEFAULT_STATUS_FIELD = "Status"


# ─────────────────────────────────────────────────────────
# Config loading
# ─────────────────────────────────────────────────────────


def _load_toml(path: Path) -> dict:
    """Best-effort TOML load. Supports tomllib (3.11+) and tomli (3.10+)."""
    if not path.exists():
        return {}
    try:
        import tomllib  # type: ignore

        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        pass
    try:
        import tomli  # type: ignore

        with open(path, "rb") as f:
            return tomli.load(f)
    except Exception:
        pass
    # Minimal fallback: parse a few known keys with regex.
    return _parse_minimal_toml(path.read_text(encoding="utf-8"))


def _parse_minimal_toml(text: str) -> dict:
    """Parse just enough TOML to read agent.binary, ticket.project and project.status_map."""
    config: dict = {"agent": {}, "ticket": {}, "project": {}}
    section = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        sec_match = re.match(r"^\[(\w+)\]", line)
        if sec_match:
            section = sec_match.group(1)
            continue
        key_match = re.match(r'^(\w+)\s*=\s*"?([^"]+)"?', line)
        if not key_match:
            continue
        key, val = key_match.group(1), key_match.group(2)
        if section == "agent":
            config["agent"][key] = val
        elif section == "ticket":
            if key == "project":
                try:
                    config["ticket"]["project"] = int(val)
                except ValueError:
                    config["ticket"]["project"] = val
            else:
                config["ticket"][key] = val
    return config


def _get_config() -> dict:
    """Return the parsed config toml."""
    return _load_toml(CONFIG_FILE)


def _project_number(config: dict) -> Optional[int]:
    """Resolve project number from env var or config."""
    env = os.environ.get("RALPH_GITHUB_PROJECT", "").strip()
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    val = config.get("ticket", {}).get("project")
    if val is None or val == "":
        return None
    try:
        num = int(val)
        return num if num > 0 else None
    except (ValueError, TypeError):
        return None


def _status_field(config: dict) -> str:
    """Return the configured Status field name."""
    return config.get("project", {}).get("status_field", DEFAULT_STATUS_FIELD)


def _status_map(config: dict) -> dict:
    """Return the configured label -> column mapping."""
    return config.get("project", {}).get("status_map", DEFAULT_STATUS_MAP)


# ─────────────────────────────────────────────────────────
# GraphQL helpers
# ─────────────────────────────────────────────────────────


def _gh_graphql(query: str, variables: dict) -> dict:
    """Run a GitHub GraphQL query via gh and return the JSON payload."""
    # Use -F so gh correctly types numeric/boolean GraphQL variables.
    cmd = ["gh", "api", "graphql", "-F", f"query={query}"]
    for key, value in variables.items():
        cmd.extend(["-F", f"{key}={value}"])
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"gh graphql failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data.get("data", {})


def _get_repo_owner_name(config: dict) -> tuple[str, str]:
    """Extract (owner, name) from git remote or config."""
    repo = config.get("ticket", {}).get("repo", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return owner, name
    # Fall back to git remote origin.
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError("no git remote origin")
    url = result.stdout.strip()
    for prefix in ["https://github.com/", "git@github.com:"]:
        if url.startswith(prefix):
            path = url[len(prefix) :]
            if path.endswith(".git"):
                path = path[:-4]
            owner, name = path.split("/", 1)
            return owner, name
    raise RuntimeError(f"cannot parse repo from remote: {url}")


def _get_issue_node_id(issue_num: int) -> str:
    """Return the GitHub node ID for an issue."""
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_num), "--json", "id"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cannot fetch issue #{issue_num}: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    return data["id"]


def _get_project_id(owner: str, name: str, project_number: int) -> str:
    """
    Return the node ID of a project by owner/name/number.

    Tries repository-level first, then organization-level, then user-level.
    """
    # 1. Repository-level project
    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        projectV2(number: $number) {
          id
        }
      }
    }
    """
    data = _gh_graphql(query, {"owner": owner, "name": name, "number": project_number})
    project = data.get("repository", {}).get("projectV2")
    if project:
        return project["id"]

    # 2. Organization-level project
    query = """
    query($login: String!, $number: Int!) {
      organization(login: $login) {
        projectV2(number: $number) {
          id
        }
      }
    }
    """
    data = _gh_graphql(query, {"login": owner, "number": project_number})
    project = data.get("organization", {}).get("projectV2")
    if project:
        return project["id"]

    # 3. User-level project
    query = """
    query($login: String!, $number: Int!) {
      user(login: $login) {
        projectV2(number: $number) {
          id
        }
      }
    }
    """
    data = _gh_graphql(query, {"login": owner, "number": project_number})
    project = data.get("user", {}).get("projectV2")
    if project:
        return project["id"]

    raise RuntimeError(
        f"project #{project_number} not found for {owner}/{name}, org {owner}, or user {owner}"
    )


def _get_project_status_field(project_id: str, field_name: str) -> dict:
    """Return the Status field definition incl. option IDs."""
    query = """
    query($projectId: ID!, $fieldName: String!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          field(name: $fieldName) {
            ... on ProjectV2SingleSelectField {
              id
              name
              options {
                id
                name
              }
            }
          }
        }
      }
    }
    """
    data = _gh_graphql(query, {"projectId": project_id, "fieldName": field_name})
    field = data.get("node", {}).get("field")
    if not field:
        raise RuntimeError(f"Status field '{field_name}' not found on project")
    return field


def _find_project_item(issue_node_id: str, project_id: str) -> Optional[str]:
    """Return the project item node ID for the issue on the given project."""
    query = """
    query($issueId: ID!) {
      node(id: $issueId) {
        ... on Issue {
          projectItems(first: 100) {
            nodes {
              id
              project {
                id
              }
            }
          }
        }
      }
    }
    """
    data = _gh_graphql(query, {"issueId": issue_node_id})
    items = data.get("node", {}).get("projectItems", {}).get("nodes", [])
    for item in items:
        if item.get("project", {}).get("id") == project_id:
            return item["id"]
    return None


def _add_issue_to_project(issue_node_id: str, project_id: str) -> str:
    """Add an issue to a project and return the item node ID."""
    mutation = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item {
          id
        }
      }
    }
    """
    data = _gh_graphql(mutation, {"projectId": project_id, "contentId": issue_node_id})
    item = data.get("addProjectV2ItemById", {}).get("item")
    if not item:
        raise RuntimeError("failed to add issue to project")
    return item["id"]


def _set_project_status(
    project_id: str, item_id: str, field_id: str, option_id: str
) -> None:
    """Set the Status field on a project item."""
    mutation = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
      updateProjectV2ItemFieldValue(
        input: {
          projectId: $projectId
          itemId: $itemId
          fieldId: $fieldId
          value: { singleSelectOptionId: $optionId }
        }
      ) {
        projectV2Item {
          id
        }
      }
    }
    """
    _gh_graphql(
        mutation,
        {
            "projectId": project_id,
            "itemId": item_id,
            "fieldId": field_id,
            "optionId": option_id,
        },
    )


# ─────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────


def sync_status(issue_num: int, status_label: str):
    """
    Mirror a Ralph status label to the GitHub Project board column.

    Args:
        issue_num: GitHub issue number.
        status_label: The new Ralph status label (e.g. "status:ready").
    """
    if not project_enabled():
        # Board sync is not enabled; labels remain the source of truth.
        return

    config = _get_config()
    project_number = _project_number(config)
    if not project_number:
        # No project configured; nothing to sync.
        return

    status_map = _status_map(config)
    column_name = status_map.get(status_label)
    if not column_name:
        # This label is not part of the board mapping.
        return

    try:
        owner, name = _get_repo_owner_name(config)
        issue_node_id = _get_issue_node_id(issue_num)
        project_id = _get_project_id(owner, name, project_number)
        field = _get_project_status_field(project_id, _status_field(config))

        option_id = None
        for opt in field.get("options", []):
            if opt["name"] == column_name:
                option_id = opt["id"]
                break
        if not option_id:
            raise RuntimeError(
                f"column '{column_name}' not found in project Status options"
            )

        item_id = _find_project_item(issue_node_id, project_id)
        if not item_id:
            item_id = _add_issue_to_project(issue_node_id, project_id)

        _set_project_status(project_id, item_id, field["id"], option_id)
        print(f"[ralph] #{issue_num} board: {column_name}")
    except Exception as e:
        # Fail-soft: board sync must never break the pipeline.
        print(f"[ralph] WARNING: could not sync board for #{issue_num}: {e}")


def sync_closed(issue_num: int):
    """
    Mirror a closed issue to the board. Uses the optional 'closed' key in the
    status_map (defaulting to 'Done' if present on the board).
    """
    if not project_enabled():
        return

    config = _get_config()
    project_number = _project_number(config)
    if not project_number:
        return

    status_map = _status_map(config)
    column_name = status_map.get("closed", "Done")
    if column_name is None:
        return

    try:
        owner, name = _get_repo_owner_name(config)
        issue_node_id = _get_issue_node_id(issue_num)
        project_id = _get_project_id(owner, name, project_number)
        field = _get_project_status_field(project_id, _status_field(config))

        option_id = None
        for opt in field.get("options", []):
            if opt["name"] == column_name:
                option_id = opt["id"]
                break
        if not option_id:
            raise RuntimeError(
                f"column '{column_name}' not found in project Status options"
            )

        item_id = _find_project_item(issue_node_id, project_id)
        if not item_id:
            item_id = _add_issue_to_project(issue_node_id, project_id)

        _set_project_status(project_id, item_id, field["id"], option_id)
        print(f"[ralph] #{issue_num} board: {column_name}")
    except Exception as e:
        print(f"[ralph] WARNING: could not sync board for #{issue_num}: {e}")


def project_configured() -> bool:
    """Return True if a GitHub project is configured for syncing."""
    return _project_number(_get_config()) is not None


def project_enabled() -> bool:
    """
    Return True if board sync should run.

    Sync is enabled when ticket.project is set, unless the user explicitly
    opts out via RALPH_PROJECT_SYNC=0. RALPH_PROJECT_SYNC=1 can force it on
    for testing, but still requires a project number to be useful.
    """
    env = os.environ.get("RALPH_PROJECT_SYNC", "").strip()
    if env == "0":
        return False
    if env == "1":
        return project_configured()
    return project_configured()


def check_project_access() -> tuple[bool, str]:
    """
    Verify that the current gh token can access the configured project.
    Returns (ok, detail).
    """
    config = _get_config()
    project_number = _project_number(config)
    if not project_number:
        return True, "no project configured"

    try:
        owner, name = _get_repo_owner_name(config)
        _get_project_id(owner, name, project_number)
        return True, f"project #{project_number} accessible"
    except Exception as e:
        return False, str(e)

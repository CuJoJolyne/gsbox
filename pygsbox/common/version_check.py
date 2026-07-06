"""HTTP version check for gsbox updates."""
import json
import urllib.request
import urllib.error
from typing import Optional

VER = "v4.8.4"
REPO_URL = "https://api.github.com/repos/gotoeasy/gsbox/releases/latest"
TIMEOUT = 5


def _parse_version(v: str) -> tuple:
    """Parse 'v4.8.4' -> (4, 8, 4) for comparison."""
    return tuple(int(x) for x in v.lstrip("v").split("."))


def check_update() -> str:
    """Check for the latest release on GitHub, compare to VER.

    Returns a multi-line status message. On any failure, returns a safe fallback.
    """
    try:
        req = urllib.request.Request(
            REPO_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"pygsbox/{VER}",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
        rel = json.loads(body)
        latest_tag = rel.get("tag_name") or rel.get("name") or "unknown"
        latest_url = rel.get("html_url") or REPO_URL
    except (urllib.error.URLError, json.JSONDecodeError, OSError, ValueError) as err:
        return (
            f"Current version: {VER}\n"
            f"Failed to check for updates: {err.__class__.__name__}: {err}"
        )

    msg = f"Current version: {VER}\n"
    msg += f"Latest release: {latest_tag}\n"
    try:
        if _parse_version(latest_tag) > _parse_version(VER):
            msg += f"Update available! See: {latest_url}"
        else:
            msg += "You are up to date."
    except (ValueError, TypeError):
        msg += f"(Could not compare versions. See: {latest_url})"
    return msg

"""
Fetch a learner's submitted GitHub repository so it can be assessed.

For PUBLIC repos this works with no credentials via the GitHub REST API.
For PRIVATE repos the learner must "grant us access" — that requires either a
GitHub App installation token or a user OAuth token. That integration point is
stubbed (`_auth_headers`); set GITHUB_TOKEN in the environment to raise rate
limits and reach private repos the token can see. Mirrors the SMS stub pattern.

We pull a curated, size-bounded slice of source files (skipping binaries,
vendored deps, lockfiles) and concatenate them for the AI assessor.
"""
import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

# Only assess real source; skip noise.
_SKIP_DIRS = ("node_modules/", ".git/", "dist/", "build/", "venv/", ".venv/",
              "__pycache__/", "vendor/", ".dart_tool/", "Pods/")
_SKIP_FILES = ("package-lock.json", "yarn.lock", "pubspec.lock", "Pipfile.lock", "poetry.lock")
_CODE_EXT = (".py", ".js", ".ts", ".jsx", ".tsx", ".dart", ".java", ".go", ".rb",
             ".rs", ".c", ".cpp", ".h", ".cs", ".php", ".html", ".css", ".sql",
             ".kt", ".swift", ".sh", ".md", ".json", ".yaml", ".yml")
_MAX_FILES = 40
_MAX_FILE_BYTES = 40_000
_MAX_TOTAL_BYTES = 200_000


class RepoError(Exception):
    pass


def _auth_headers():
    headers = {"Accept": "application/vnd.github+json"}
    token = getattr(settings, "GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def parse_repo(url: str):
    """Return (owner, repo) from a GitHub URL, or raise RepoError."""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/#?]+?)(?:\.git)?/?$", url.strip())
    if not m:
        raise RepoError("That doesn't look like a GitHub repository URL.")
    return m.group(1), m.group(2)


def fetch_repo_text(url: str) -> str:
    """
    Download a bounded, concatenated snapshot of source files from the repo's
    default branch. Raises RepoError on access problems (so callers can tell the
    learner to make the repo public or grant access).
    """
    owner, repo = parse_repo(url)
    headers = _auth_headers()

    meta = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=headers, timeout=20)
    if meta.status_code == 404:
        raise RepoError("Repository not found. Make it public, or grant us access.")
    if meta.status_code == 403:
        raise RepoError("Access denied / rate-limited. Set GITHUB_TOKEN or make the repo public.")
    meta.raise_for_status()
    branch = meta.json().get("default_branch", "main")

    tree = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
        headers=headers, timeout=30,
    )
    tree.raise_for_status()
    entries = [e for e in tree.json().get("tree", []) if e.get("type") == "blob"]

    chunks, total, count = [], 0, 0
    raw_base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/"
    for e in entries:
        path = e["path"]
        if count >= _MAX_FILES or total >= _MAX_TOTAL_BYTES:
            break
        if any(path.startswith(d) or f"/{d}" in path for d in _SKIP_DIRS):
            continue
        if path.split("/")[-1] in _SKIP_FILES:
            continue
        if not path.lower().endswith(_CODE_EXT):
            continue
        if e.get("size", 0) > _MAX_FILE_BYTES:
            continue
        try:
            r = requests.get(raw_base + path, headers=headers, timeout=20)
            if r.status_code == 200 and r.text:
                body = r.text[:_MAX_FILE_BYTES]
                chunks.append(f"\n===== FILE: {path} =====\n{body}")
                total += len(body)
                count += 1
        except requests.RequestException:
            continue

    if not chunks:
        raise RepoError("No readable source files found in the repository.")
    logger.info("Fetched %s files (%s bytes) from %s/%s", count, total, owner, repo)
    return "".join(chunks)

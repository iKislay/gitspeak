import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Generator
from github import Github, Repository, PullRequest, Commit, GitTree
from github.GithubException import RateLimitExceededException, UnknownObjectException
import httpx

from config import (
    GITHUB_TOKEN,
    INGEST_SOURCE_FILES,
    MAX_FILE_SIZE_BYTES,
    MAX_SOURCE_FILES,
    INGESTED_EXTENSIONS,
    SKIP_PATH_PATTERNS,
)

logger = logging.getLogger(__name__)


class GithubFetcher:
    """
    Fetches raw repository data from GitHub including README, PRs, Commits,
    File Tree, and actual source file contents.
    Also provides interactive utility methods for on-demand exploration.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or GITHUB_TOKEN
        self.gh = Github(self.token)

    # ─────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────

    def _handle_rate_limit(self, func, *args, **kwargs) -> Any:
        """Exponential backoff for GitHub API rate limiting."""
        retries = 3
        backoff = 2
        for i in range(retries):
            try:
                return func(*args, **kwargs)
            except RateLimitExceededException:
                logger.warning(f"Rate limited. Sleeping for {backoff}s...")
                time.sleep(backoff)
                backoff *= 2
        return func(*args, **kwargs)

    def _safe_iterate(self, paginated_list, limit: int) -> Generator[Any, None, None]:
        """Safely iterate a PyGithub PaginatedList with rate limit handling."""
        count = 0
        iterator = iter(paginated_list)
        while count < limit:
            try:
                item = self._handle_rate_limit(next, iterator)
                yield item
                count += 1
            except StopIteration:
                break
            except Exception as e:
                logger.error(f"Pagination error: {e}")
                break

    def _get_repo(self, repo_slug: str) -> Optional[Repository.Repository]:
        try:
            return self._handle_rate_limit(self.gh.get_repo, repo_slug)
        except Exception as e:
            logger.error(f"Failed to access {repo_slug}: {e}")
            return None

    def _should_skip_path(self, path: str) -> bool:
        """Return True if any path segment is in SKIP_PATH_PATTERNS."""
        parts = path.split("/")
        return any(part in SKIP_PATH_PATTERNS for part in parts)

    def _ext(self, path: str) -> str:
        _, ext = os.path.splitext(path)
        return ext.lower()

    # ─────────────────────────────────────────────────────────────────
    # Primary ingestion entrypoint
    # ─────────────────────────────────────────────────────────────────

    def fetch_all(self, repo_slug: str) -> List[Dict[str, Any]]:
        """
        Main entry point. Fetches README, file tree, PRs, commits, and (if
        enabled) actual source file contents.
        """
        logger.info(f"Starting full fetch for {repo_slug}")
        repo = self._get_repo(repo_slug)
        if not repo:
            return []

        items = []

        # 1. README
        try:
            readme = self._handle_rate_limit(repo.get_readme)
            items.append({
                "type": "readme",
                "id": "readme",
                "title": "Repository README",
                "content": readme.decoded_content.decode("utf-8"),
                "author": repo.owner.login,
                "date": repo.updated_at.isoformat(),
                "url": readme.html_url,
                "repo": repo_slug,
            })
            logger.info("Fetched README.")
        except Exception as e:
            logger.warning(f"README fetch failed: {e}")

        # 2. File Tree (2-level depth)
        try:
            tree: GitTree.GitTree = self._handle_rate_limit(
                repo.get_git_tree, repo.default_branch, recursive=True
            )
            tree_content = [
                f"{el.path} ({el.type})"
                for el in tree.tree
                if el.path.count("/") < 2
            ]
            items.append({
                "type": "file_tree",
                "id": "file_tree",
                "title": "Repository File Tree",
                "content": "\n".join(tree_content),
                "author": repo.owner.login,
                "date": repo.updated_at.isoformat(),
                "url": repo.html_url,
                "repo": repo_slug,
            })
            logger.info("Fetched File Tree.")
        except Exception as e:
            logger.warning(f"File tree fetch failed: {e}")

        # 3. Merged Pull Requests (up to 500)
        try:
            raw_prs = repo.get_pulls(state="closed", sort="created", direction="desc")
            pr_count = 0
            for pr in self._safe_iterate(raw_prs, limit=1000):
                if pr_count >= 500:
                    break
                if pr.merged_at:
                    changed_files = []
                    try:
                        pr_files = self._handle_rate_limit(pr.get_files)
                        changed_files = [f.filename for i, f in enumerate(pr_files) if i < 50]
                    except Exception:
                        pass

                    content = pr.body or pr.title
                    file_list_str = "\n".join(changed_files)
                    full_content = f"{content}\n\nFiles changed:\n{file_list_str}"

                    items.append({
                        "type": "pr",
                        "id": str(pr.number),
                        "title": pr.title,
                        "content": full_content,
                        "author": pr.user.login if pr.user else "Unknown",
                        "date": pr.merged_at.isoformat(),
                        "url": pr.html_url,
                        "repo": repo_slug,
                    })
                    pr_count += 1
            logger.info(f"Fetched {pr_count} merged PRs.")
        except Exception as e:
            logger.warning(f"PR fetch failed: {e}")

        # 4. Commits (up to 500)
        try:
            raw_commits = repo.get_commits()
            commit_count = 0
            for commit in self._safe_iterate(raw_commits, limit=1000):
                if commit_count >= 500:
                    break
                content = commit.commit.message
                title = content.split("\n")[0] if content else "No Message"

                changed_files = []
                if commit.files:
                    changed_files = [f.filename for i, f in enumerate(commit.files) if i < 50]

                file_list_str = "\n".join(changed_files)
                full_content = f"{content}\n\nFiles changed:\n{file_list_str}"

                author_login = (
                    commit.author.login
                    if commit.author
                    else (commit.commit.author.name if commit.commit.author else "Unknown")
                )
                date_iso = (
                    commit.commit.author.date.isoformat()
                    if commit.commit.author
                    else repo.updated_at.isoformat()
                )

                items.append({
                    "type": "commit",
                    "id": commit.sha,
                    "title": title,
                    "content": full_content,
                    "author": author_login,
                    "date": date_iso,
                    "url": commit.html_url,
                    "repo": repo_slug,
                })
                commit_count += 1
            logger.info(f"Fetched {commit_count} commits.")
        except Exception as e:
            logger.warning(f"Commit fetch failed: {e}")

        # 5. Source Files (if enabled)
        if INGEST_SOURCE_FILES:
            source_items = self.fetch_source_files(repo_slug, repo=repo)
            items.extend(source_items)

        logger.info(f"Completed fetch for {repo_slug}. Total items: {len(items)}")
        return items

    # ─────────────────────────────────────────────────────────────────
    # Feature 1: Deep Code Ingestion
    # ─────────────────────────────────────────────────────────────────

    def fetch_source_files(
        self,
        repo_slug: str,
        repo: Optional[Repository.Repository] = None,
    ) -> List[Dict[str, Any]]:
        """
        Ingest actual source file contents. Respects MAX_FILE_SIZE_BYTES,
        MAX_SOURCE_FILES, INGESTED_EXTENSIONS, and SKIP_PATH_PATTERNS.
        """
        if repo is None:
            repo = self._get_repo(repo_slug)
        if not repo:
            return []

        logger.info(f"Starting source file ingestion for {repo_slug}")
        items = []

        try:
            tree: GitTree.GitTree = self._handle_rate_limit(
                repo.get_git_tree, repo.default_branch, recursive=True
            )
        except Exception as e:
            logger.error(f"Cannot fetch tree for source ingestion: {e}")
            return []

        eligible = [
            el for el in tree.tree
            if el.type == "blob"
            and not self._should_skip_path(el.path)
            and self._ext(el.path) in INGESTED_EXTENSIONS
            and (el.size or 0) <= MAX_FILE_SIZE_BYTES
        ]

        logger.info(f"Found {len(eligible)} eligible source files (cap: {MAX_SOURCE_FILES})")
        eligible = eligible[:MAX_SOURCE_FILES]

        for el in eligible:
            try:
                file_content = self._handle_rate_limit(repo.get_contents, el.path)
                if file_content.encoding == "base64" or file_content.content:
                    decoded = file_content.decoded_content.decode("utf-8", errors="replace")
                else:
                    continue

                language = self._ext(el.path).lstrip(".")
                items.append({
                    "type": "source_file",
                    "id": el.path,
                    "title": f"Source file: {el.path}",
                    "content": decoded,
                    "language": language,
                    "path": el.path,
                    "author": repo.owner.login,
                    "date": repo.updated_at.isoformat(),
                    "url": f"https://github.com/{repo_slug}/blob/{repo.default_branch}/{el.path}",
                    "repo": repo_slug,
                })
            except Exception as e:
                logger.debug(f"Skipping {el.path}: {e}")

        logger.info(f"Ingested {len(items)} source files from {repo_slug}.")
        return items

    # ─────────────────────────────────────────────────────────────────
    # Feature 2: Interactive Tool Calling — utility methods
    # ─────────────────────────────────────────────────────────────────

    def read_file(self, repo_slug: str, path: str) -> Dict[str, Any]:
        """
        Read the content of a single file from the repo.
        Returns a dict with 'content', 'path', 'url', or 'error'.
        """
        repo = self._get_repo(repo_slug)
        if not repo:
            return {"error": f"Cannot access repository {repo_slug}."}
        try:
            fc = self._handle_rate_limit(repo.get_contents, path)
            if isinstance(fc, list):
                # path is a directory
                names = [f.name for f in fc]
                return {
                    "error": f"'{path}' is a directory, not a file. Contents: {', '.join(names)}"
                }
            content = fc.decoded_content.decode("utf-8", errors="replace")
            return {
                "path": path,
                "content": content,
                "url": fc.html_url,
                "size": fc.size,
            }
        except UnknownObjectException:
            return {"error": f"File '{path}' not found in {repo_slug}."}
        except Exception as e:
            return {"error": f"Could not read '{path}': {e}"}

    def list_directory(self, repo_slug: str, path: str = "") -> Dict[str, Any]:
        """
        List the contents of a directory in the repo.
        Returns a dict with 'entries' (list of {name, type}) or 'error'.
        """
        repo = self._get_repo(repo_slug)
        if not repo:
            return {"error": f"Cannot access repository {repo_slug}."}
        try:
            contents = self._handle_rate_limit(repo.get_contents, path or "")
            if not isinstance(contents, list):
                return {"error": f"'{path}' is a file, not a directory."}
            entries = [{"name": f.name, "type": f.type} for f in contents]
            return {"path": path or "/", "entries": entries}
        except UnknownObjectException:
            return {"error": f"Directory '{path}' not found in {repo_slug}."}
        except Exception as e:
            return {"error": f"Could not list '{path}': {e}"}

    def get_commit_diff(self, repo_slug: str, sha: str) -> Dict[str, Any]:
        """
        Get the file patches introduced by a specific commit SHA.
        Returns {'sha', 'message', 'files': [{filename, patch, additions, deletions}]} or 'error'.
        """
        repo = self._get_repo(repo_slug)
        if not repo:
            return {"error": f"Cannot access repository {repo_slug}."}
        try:
            commit = self._handle_rate_limit(repo.get_commit, sha)
            files = []
            for f in (commit.files or [])[:20]:  # cap at 20 files
                files.append({
                    "filename": f.filename,
                    "patch": (f.patch or "")[:2000],  # cap patch size
                    "additions": f.additions,
                    "deletions": f.deletions,
                })
            return {
                "sha": commit.sha,
                "message": commit.commit.message,
                "author": commit.commit.author.name if commit.commit.author else "Unknown",
                "date": commit.commit.author.date.isoformat() if commit.commit.author else "",
                "files": files,
            }
        except UnknownObjectException:
            return {"error": f"Commit '{sha}' not found in {repo_slug}."}
        except Exception as e:
            return {"error": f"Could not fetch commit diff: {e}"}

    # ─────────────────────────────────────────────────────────────────
    # Feature 3: Standup Mode — recent activity
    # ─────────────────────────────────────────────────────────────────

    def fetch_recent_activity(
        self, repo_slug: str, since_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Fetch all activity in the repo within the last `since_hours` hours.
        Returns a dict with 'merged_prs', 'commits', 'open_prs_updated'.
        """
        repo = self._get_repo(repo_slug)
        if not repo:
            return {"error": f"Cannot access repository {repo_slug}."}

        since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        activity: Dict[str, Any] = {
            "repo": repo_slug,
            "window_hours": since_hours,
            "since": since_dt.isoformat(),
            "merged_prs": [],
            "commits": [],
            "open_prs_updated": [],
        }

        # Merged PRs in window
        try:
            raw_prs = repo.get_pulls(state="closed", sort="updated", direction="desc")
            for pr in self._safe_iterate(raw_prs, limit=200):
                if pr.merged_at and pr.merged_at.replace(tzinfo=timezone.utc) >= since_dt:
                    activity["merged_prs"].append({
                        "number": pr.number,
                        "title": pr.title,
                        "author": pr.user.login if pr.user else "Unknown",
                        "merged_at": pr.merged_at.isoformat(),
                        "url": pr.html_url,
                    })
                elif pr.updated_at.replace(tzinfo=timezone.utc) < since_dt:
                    break  # sorted by updated desc, safe to stop
        except Exception as e:
            logger.warning(f"PR activity fetch failed: {e}")

        # Recent commits
        try:
            raw_commits = repo.get_commits(since=since_dt)
            for commit in self._safe_iterate(raw_commits, limit=100):
                message = commit.commit.message or ""
                activity["commits"].append({
                    "sha": commit.sha[:7],
                    "message": message.split("\n")[0],
                    "author": (
                        commit.author.login if commit.author
                        else (commit.commit.author.name if commit.commit.author else "Unknown")
                    ),
                    "date": commit.commit.author.date.isoformat() if commit.commit.author else "",
                    "url": commit.html_url,
                })
        except Exception as e:
            logger.warning(f"Commit activity fetch failed: {e}")

        # Open PRs with recent updates
        try:
            open_prs = repo.get_pulls(state="open", sort="updated", direction="desc")
            for pr in self._safe_iterate(open_prs, limit=100):
                if pr.updated_at.replace(tzinfo=timezone.utc) >= since_dt:
                    activity["open_prs_updated"].append({
                        "number": pr.number,
                        "title": pr.title,
                        "author": pr.user.login if pr.user else "Unknown",
                        "updated_at": pr.updated_at.isoformat(),
                        "url": pr.html_url,
                    })
                else:
                    break
        except Exception as e:
            logger.warning(f"Open PR activity fetch failed: {e}")

        logger.info(
            f"Activity for {repo_slug} (last {since_hours}h): "
            f"{len(activity['merged_prs'])} merged PRs, "
            f"{len(activity['commits'])} commits, "
            f"{len(activity['open_prs_updated'])} updated open PRs"
        )
        return activity

import logging
import time
from typing import Dict, List, Any, Optional, Generator
from github import Github, Repository, PullRequest, Commit, GitTree
from github.GithubException import RateLimitExceededException
import httpx

from config import GITHUB_TOKEN

logger = logging.getLogger(__name__)

class GithubFetcher:
    """
    Fetches raw repository data from GitHub including README, PRs, Commits, and File Tree.
    Handles rate limiting and pagination for large repositories.
    """
    def __init__(self, token: Optional[str] = None):
        """
        Initialize GithubFetcher with a token.
        """
        self.token = token or GITHUB_TOKEN
        self.gh = Github(self.token)

    def _handle_rate_limit(self, func, *args, **kwargs) -> Any:
        """Simple exponential backoff for rate limiting on direct API calls."""
        retries = 3
        backoff = 2
        for i in range(retries):
            try:
                return func(*args, **kwargs)
            except RateLimitExceededException:
                logger.warning(f"Rate limited. Sleeping for {backoff} seconds...")
                time.sleep(backoff)
                backoff *= 2
        # If still failing, it will raise for the caller to handle
        return func(*args, **kwargs)

    def _safe_iterate(self, paginated_list, limit: int) -> Generator[Any, None, None]:
        """Safely iterate over a PyGithub PaginatedList handling rate limits."""
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
                logger.error(f"Error during pagination: {e}")
                break

    def fetch_all(self, repo_slug: str) -> List[Dict[str, Any]]:
        """
        Main entry point to fetch all required components for the codebase oracle.
        
        Args:
            repo_slug: The owner/repo string for GitHub.
            
        Returns:
            A list of dicts containing metadata and content for various repo items.
        """
        logger.info(f"Starting fetch for {repo_slug}")
        try:
            repo: Repository.Repository = self._handle_rate_limit(self.gh.get_repo, repo_slug)
        except Exception as e:
            logger.error(f"Failed to access repository {repo_slug}: {e}")
            return []
        
        items = []
        
        # 1. Fetch README
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
                "repo": repo_slug
            })
            logger.info("Fetched README.")
        except Exception as e:
            logger.warning(f"Failed to fetch README for {repo_slug}: {e}")

        # 2. Fetch File Tree (up to 2 levels)
        try:
            tree: GitTree.GitTree = self._handle_rate_limit(repo.get_git_tree, repo.default_branch, recursive=True)
            tree_content = []
            for element in tree.tree:
                # Count the depth of the file path
                depth = element.path.count('/')
                if depth < 2:
                    tree_content.append(f"{element.path} ({element.type})")
            
            items.append({
                "type": "file_tree",
                "id": "file_tree",
                "title": "Repository File Tree",
                "content": "\n".join(tree_content),
                "author": repo.owner.login,
                "date": repo.updated_at.isoformat(),
                "url": repo.html_url,
                "repo": repo_slug
            })
            logger.info("Fetched File Tree.")
        except Exception as e:
            logger.warning(f"Failed to fetch file tree for {repo_slug}: {e}")

        # 3. Fetch Pull Requests (Merged only, limited to 500)
        try:
            # Note: PyGithub doesn't have a direct "merged" filter for get_pulls(), only state="closed".
            # We filter for merged properties afterwards.
            raw_prs = repo.get_pulls(state='closed', sort='created', direction='desc')
            pr_count = 0
            
            # We use a larger limit for raw iteration to find 500 merged ones
            for pr in self._safe_iterate(raw_prs, limit=1000):
                if pr_count >= 500:
                    break
                if pr.merged_at:
                    content = pr.body or pr.title # If body empty, fallback to title
                    
                    # Fetching files can take an extra API call per PR.
                    changed_files = []
                    try:
                        pr_files = self._handle_rate_limit(pr.get_files)
                        # We only grab first 50 files per PR to avoid bloat
                        changed_files = [f.filename for i, f in enumerate(pr_files) if i < 50]
                    except Exception as e:
                        logger.debug(f"Failed to fetch files for PR {pr.number}: {e}")
                    
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
                        "repo": repo_slug
                    })
                    pr_count += 1
            logger.info(f"Fetched {pr_count} merged PRs.")
        except Exception as e:
            logger.warning(f"Failed to fetch PRs for {repo_slug}: {e}")

        # 4. Fetch Commits (last 1000)
        try:
            raw_commits = repo.get_commits()
            commit_count = 0
            for commit in self._safe_iterate(raw_commits, limit=1000):
                content = commit.commit.message
                title = content.split('\n')[0] if content else "No Message"
                
                # We only grab first 50 files per commit to avoid bloat
                changed_files = []
                if commit.files:
                    changed_files = [f.filename for i, f in enumerate(commit.files) if i < 50]
                
                file_list_str = "\n".join(changed_files)
                full_content = f"{content}\n\nFiles changed:\n{file_list_str}"
                
                author_login = commit.author.login if commit.author else (commit.commit.author.name if commit.commit.author else "Unknown")
                date_iso = commit.commit.author.date.isoformat() if commit.commit.author else repo.updated_at.isoformat()
                
                items.append({
                    "type": "commit",
                    "id": commit.sha,
                    "title": title,
                    "content": full_content,
                    "author": author_login,
                    "date": date_iso,
                    "url": commit.html_url,
                    "repo": repo_slug
                })
                commit_count += 1
            logger.info(f"Fetched {commit_count} commits.")
        except Exception as e:
            logger.warning(f"Failed to fetch commits for {repo_slug}: {e}")

        logger.info(f"Completed fetching for {repo_slug}. Total items: {len(items)}")
        return items


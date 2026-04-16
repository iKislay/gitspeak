import logging
from typing import List, Optional, Dict, Any

from github import Github
from github.GithubException import UnknownObjectException

from config import GITHUB_TOKEN

logger = logging.getLogger(__name__)

_gh = Github(GITHUB_TOKEN)


def create_issue(
    repo_slug: str,
    title: str,
    body: str = "",
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create a GitHub issue in the specified repository.
    Returns {'number', 'url', 'title'} on success or {'error': str}.
    """
    try:
        repo = _gh.get_repo(repo_slug)
        kwargs: Dict[str, Any] = {"title": title, "body": body}
        if labels:
            kwargs["labels"] = labels
        if assignees:
            kwargs["assignees"] = assignees

        issue = repo.create_issue(**kwargs)
        logger.info(f"Created issue #{issue.number} in {repo_slug}: '{title}'")
        return {
            "number": issue.number,
            "title": issue.title,
            "url": issue.html_url,
        }
    except UnknownObjectException:
        return {"error": f"Repository '{repo_slug}' not found or insufficient permissions."}
    except Exception as e:
        logger.error(f"Failed to create issue in {repo_slug}: {e}")
        return {"error": str(e)}


def trigger_workflow(
    repo_slug: str,
    workflow_id: str,
    ref: str = "main",
    inputs: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Trigger a GitHub Actions workflow_dispatch event.
    `workflow_id` can be a workflow filename (e.g. 'deploy.yml') or numeric ID.
    Returns {'status': 'triggered', 'workflow': ..., 'ref': ...} or {'error': str}.
    """
    try:
        repo = _gh.get_repo(repo_slug)

        # Try numeric ID first, then filename
        try:
            wf_id = int(workflow_id)
            workflow = repo.get_workflow(wf_id)
        except (ValueError, UnknownObjectException):
            workflow = repo.get_workflow(workflow_id)

        workflow.create_dispatch(ref=ref, inputs=inputs or {})
        logger.info(f"Triggered workflow '{workflow.name}' on {repo_slug}@{ref}")
        return {
            "status": "triggered",
            "workflow": workflow.name,
            "ref": ref,
            "url": f"https://github.com/{repo_slug}/actions",
        }
    except UnknownObjectException:
        return {
            "error": f"Workflow '{workflow_id}' not found in {repo_slug}. "
                     f"Check that the workflow file has a 'workflow_dispatch' trigger."
        }
    except Exception as e:
        logger.error(f"Failed to trigger workflow in {repo_slug}: {e}")
        return {"error": str(e)}

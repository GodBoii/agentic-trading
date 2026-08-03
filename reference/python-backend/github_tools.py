"""GitHub toolkit exposing repository management helpers."""

import logging
from typing import Dict, List, Optional

from agno.tools import Toolkit
from github import Github, GithubException, InputGitTreeElement

from supabase_client import supabase_client

logger = logging.getLogger(__name__)


class GitHubTools(Toolkit):
    """A toolkit for interacting with the GitHub API on behalf of the user."""

    def __init__(self, user_id: str):
        """Initializes the GitHubTools toolkit."""
        super().__init__(
            name="github_tools",
            tools=[
                self.list_repositories,
                self.create_issue,
                # --- Expanded tools ---
                self.get_file_content,
                self.list_pull_requests,
                self.get_pull_request_details,
                self.add_comment,
                self.get_repository_details,
                self.list_branches,
                self.create_branch,
                self.create_or_update_file,
                self.commit_files,
            ],
        )
        self.user_id = user_id
        self._github_client: Optional[Github] = None
        self._access_token: Optional[str] = None
        self._token_fetched = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_access_token(self) -> Optional[str]:
        if self._token_fetched:
            return self._access_token
        try:
            response = (
                supabase_client.from_("user_integrations")
                .select("access_token")
                .eq("user_id", self.user_id)
                .eq("service", "github")
                .single()
                .execute()
            )
            if response.data and response.data.get("access_token"):
                self._access_token = response.data["access_token"]
            else:
                self._access_token = None
        except Exception as exc:
            logger.error("Error fetching GitHub token for user %s: %s", self.user_id, exc)
            self._access_token = None
        self._token_fetched = True
        return self._access_token

    def _get_client(self) -> Optional[Github]:
        if self._github_client:
            return self._github_client
        access_token = self._get_access_token()
        if access_token:
            self._github_client = Github(access_token)
        return self._github_client

    # ------------------------------------------------------------------
    # Core tools
    # ------------------------------------------------------------------
    def list_repositories(self) -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        try:
            repos = client.get_user().get_repos()
            repo_list = [repo.full_name for repo in repos]
            if not repo_list:
                return "No repositories found for your account."
            return "\n".join(repo_list)
        except GithubException as exc:
            message = exc.data.get("message", "Invalid credentials") if exc.data else str(exc)
            return f"Error accessing GitHub API: {message}."

    def create_issue(self, repo_full_name: str, title: str, body: str) -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        try:
            repo = client.get_repo(repo_full_name)
            issue = repo.create_issue(title=title, body=body)
            return f"Successfully created issue #{issue.number} in {repo_full_name}. URL: {issue.html_url}"
        except GithubException as exc:
            if exc.status == 404:
                return f"Error: Repository '{repo_full_name}' not found."
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error creating issue: {message}."

    # ------------------------------------------------------------------
    # Expanded tools
    # ------------------------------------------------------------------
    def get_file_content(self, repo_full_name: str, file_path: str, ref: Optional[str] = None) -> str:
        """Retrieves the contents of a file from a repository."""
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        try:
            repo = client.get_repo(repo_full_name)
            contents = repo.get_contents(file_path, ref=ref)
            decoded = contents.decoded_content
            return decoded.decode("utf-8") if isinstance(decoded, bytes) else str(decoded)
        except GithubException as exc:
            if exc.status == 404:
                return f"Error: File or repository not found at '{repo_full_name}/{file_path}'."
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error getting file content: {message}."

    def list_pull_requests(self, repo_full_name: str, state: str = "open") -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        try:
            repo = client.get_repo(repo_full_name)
            pulls = repo.get_pulls(state=state, sort="created", direction="desc")
            if pulls.totalCount == 0:
                return f"No {state} pull requests found in {repo_full_name}."
            summaries = [f"PR #{pr.number}: {pr.title} (by {pr.user.login})" for pr in pulls]
            return "\n".join(summaries)
        except GithubException as exc:
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error listing pull requests: {message}."

    def get_pull_request_details(self, repo_full_name: str, pr_number: int) -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        try:
            repo = client.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            changed_files = [f"- {file.filename}" for file in pr.get_files()]
            details = [
                f"PR #{pr.number}: {pr.title}",
                f"Author: {pr.user.login}",
                f"State: {pr.state}",
                f"URL: {pr.html_url}",
                "",
                "Description:",
                pr.body or "No description.",
                "",
                f"Files Changed ({len(changed_files)}):",
                *(changed_files or ["- None"]),
            ]
            return "\n".join(details)
        except GithubException as exc:
            if exc.status == 404:
                return f"Error: Pull request #{pr_number} not found in '{repo_full_name}'."
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error getting PR details: {message}."

    def add_comment(self, repo_full_name: str, issue_number: int, comment_body: str) -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        try:
            repo = client.get_repo(repo_full_name)
            issue = repo.get_issue(number=issue_number)
            comment = issue.create_comment(comment_body)
            return f"Successfully added comment to issue/PR #{issue_number}. URL: {comment.html_url}"
        except GithubException as exc:
            if exc.status == 404:
                return f"Error: Issue or PR #{issue_number} not found in '{repo_full_name}'."
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error adding comment: {message}."

    def get_repository_details(self, repo_full_name: str) -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        try:
            repo = client.get_repo(repo_full_name)
            details = [
                f"**Repository**: {repo.full_name}",
                f"**ID**: `{repo.id}`",
                f"**Default Branch**: {repo.default_branch}",
                f"**Visibility**: {repo.visibility}",
                f"**SSH URL**: {repo.ssh_url}",
                f"**HTTPS URL**: {repo.clone_url}",
            ]
            return "Repository details:\n" + "\n".join(details)
        except GithubException as exc:
            if exc.status == 404:
                return f"Error: Repository '{repo_full_name}' not found."
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error getting repository details: {message}."

    def list_branches(self, repo_full_name: str) -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        try:
            repo = client.get_repo(repo_full_name)
            branches = [branch.name for branch in repo.get_branches()]
            if not branches:
                return f"No branches found in {repo_full_name}."
            return "Branches:\n" + "\n".join(f"- {name}" for name in branches)
        except GithubException as exc:
            if exc.status == 404:
                return f"Error: Repository '{repo_full_name}' not found."
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error listing branches: {message}."

    def create_branch(self, repo_full_name: str, new_branch: str, from_branch: Optional[str] = None) -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        try:
            repo = client.get_repo(repo_full_name)
            source_branch = from_branch or repo.default_branch
            try:
                repo.get_git_ref(f"heads/{new_branch}")
                return f"Error: Branch '{new_branch}' already exists in {repo_full_name}."
            except GithubException as exc:
                if exc.status != 404:
                    raise

            base_ref = repo.get_git_ref(f"heads/{source_branch}")
            repo.create_git_ref(ref=f"refs/heads/{new_branch}", sha=base_ref.object.sha)
            return f"Created branch '{new_branch}' from '{source_branch}' in {repo_full_name}."
        except GithubException as exc:
            if exc.status == 404:
                return f"Error: Source branch '{from_branch or source_branch}' or repository '{repo_full_name}' not found."
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error creating branch: {message}."
        except Exception as exc:  # pragma: no cover - unexpected error logging
            logger.exception("Unexpected error creating branch")
            return f"An unexpected error occurred: {exc}"

    def create_or_update_file(
        self,
        repo_full_name: str,
        path: str,
        content: str,
        commit_message: str,
        branch: Optional[str] = None,
    ) -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        if not path:
            return "Error: File path must be provided."
        try:
            repo = client.get_repo(repo_full_name)
            target_branch = branch or repo.default_branch
            try:
                existing = repo.get_contents(path, ref=target_branch)
                repo.update_file(
                    path=path,
                    message=commit_message,
                    content=content,
                    sha=existing.sha,
                    branch=target_branch,
                )
                return f"Updated file '{path}' on branch '{target_branch}'."
            except GithubException as exc:
                if exc.status != 404:
                    raise
                repo.create_file(
                    path=path,
                    message=commit_message,
                    content=content,
                    branch=target_branch,
                )
                return f"Created file '{path}' on branch '{target_branch}'."
        except GithubException as exc:
            if exc.status == 404:
                return f"Error: Repository '{repo_full_name}' not found."
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error creating or updating file: {message}."
        except Exception as exc:  # pragma: no cover - unexpected error logging
            logger.exception("Unexpected error creating/updating file")
            return f"An unexpected error occurred: {exc}"

    def commit_files(
        self,
        repo_full_name: str,
        branch: str,
        files: List[Dict[str, str]],
        commit_message: str,
    ) -> str:
        client = self._get_client()
        if not client:
            return "GitHub account not connected."
        if not branch:
            return "Error: Branch name must be provided."
        if not files:
            return "Error: At least one file must be provided."
        try:
            repo = client.get_repo(repo_full_name)
            ref = repo.get_git_ref(f"heads/{branch}")
            base_commit = repo.get_git_commit(ref.object.sha)

            tree_elements: List[InputGitTreeElement] = []
            for file_entry in files:
                path = file_entry.get("path")
                content = file_entry.get("content")
                if not path or content is None:
                    return "Error: Each file must include 'path' and 'content'."
                blob = repo.create_git_blob(content, "utf-8")
                tree_elements.append(InputGitTreeElement(path=path, mode="100644", type="blob", sha=blob.sha))

            tree = repo.create_git_tree(tree_elements, base_tree=base_commit.tree)
            new_commit = repo.create_git_commit(commit_message, tree, [base_commit])
            ref.edit(new_commit.sha)
            return (
                f"Committed {len(files)} file(s) to branch '{branch}'. "
                f"Commit SHA: `{new_commit.sha}`"
            )
        except GithubException as exc:
            if exc.status == 404:
                return f"Error: Repository '{repo_full_name}' or branch '{branch}' not found."
            message = exc.data.get("message", "Unknown error") if exc.data else str(exc)
            return f"Error committing files: {message}."
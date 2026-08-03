# python-backend/vercel_tools.py

import logging
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

from agno.tools import Toolkit
from supabase_client import supabase_client

logger = logging.getLogger(__name__)

class VercelTools(Toolkit):
    """
    A toolkit for interacting with the Vercel API on behalf of the user.
    It allows the agent to manage projects, deployments, environment variables, and domains.
    """

    def __init__(self, user_id: str):
        """Initializes the VercelTools toolkit."""
        super().__init__(
            name="vercel_tools",
            tools=[
                # Existing Read-Only Tools
                self.list_projects,
                self.list_deployments,
                self.get_project_details,
                # --- START: New Expanded Tools ---
                self.create_project,
                self.delete_project,
                self.list_environment_variables,
                self.add_environment_variable,
                self.remove_environment_variable,
                self.trigger_redeployment,
                self.create_deployment,
                self.cancel_deployment,
                self.get_deployment_status,
                self.get_deployment_events,
                self.list_deployment_checks,
                self.create_deployment_check,
                self.update_deployment_check,
                self.update_project_settings,
                self.list_project_domains,
                self.add_project_domain,
                self.remove_project_domain,
                self.verify_project_domain,
                self.list_global_environment_variables,
                self.add_global_environment_variable,
                self.remove_global_environment_variable,
                self.get_integration_configuration,
                self.list_teams,
                self.get_current_user,
                # --- END: New Expanded Tools ---
            ],
        )
        self.user_id = user_id
        self._access_token: Optional[str] = None
        self._token_fetched = False
        self.api_base_url = "https://api.vercel.com"

    def _get_access_token(self) -> Optional[str]:
        """Retrieves the user's Vercel access token from the database."""
        if self._token_fetched:
            return self._access_token
        try:
            response = (
                supabase_client.from_("user_integrations")
                .select("access_token")
                .eq("user_id", self.user_id)
                .eq("service", "vercel")
                .single()
                .execute()
            )
            self._access_token = response.data.get("access_token") if response.data else None
        except Exception as e:
            logger.error(f"Error fetching Vercel token for user {self.user_id}: {e}")
            self._access_token = None
        self._token_fetched = True
        return self._access_token

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_payload: Optional[Dict[str, Any]] = None,
        team_id: Optional[str] = None,
    ) -> requests.Response:
        """
        A helper function to make authenticated requests to the Vercel API.
        Now supports sending a JSON payload for POST/DELETE requests.
        """
        token = self._get_access_token()
        if not token:
            raise Exception("Vercel account not connected or token is invalid.")
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"{self.api_base_url}/{endpoint}"

        merged_params = dict(params or {})
        if team_id:
            merged_params["teamId"] = team_id

        response = requests.request(method, url, headers=headers, params=merged_params, json=json_payload)
        response.raise_for_status()
        return response

    @staticmethod
    def _format_timestamp(timestamp_ms: Optional[int]) -> str:
        if not timestamp_ms:
            return "N/A"
        try:
            return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return "N/A"

    # --- Existing Tools (Unchanged) ---

    def list_projects(self) -> str:
        """Lists all projects for the connected Vercel account, including their name and framework."""
        try:
            response = self._make_request("GET", "v9/projects")
            projects = response.json().get("projects", [])
            if not projects: return "No Vercel projects were found for your account."
            summaries = [f"- **{p['name']}** (ID: `{p['id']}`, Framework: {p.get('framework', 'N/A')})" for p in projects]
            return "Here are your Vercel projects:\n" + "\n".join(summaries)
        except Exception as e:
            return f"An error occurred: {e}"

    def list_deployments(self, project_name: str, limit: int = 5) -> str:
        """Lists the most recent deployments for a specific Vercel project by its name."""
        try:
            response = self._make_request("GET", "v6/deployments", params={"appName": project_name, "limit": limit})
            deployments = response.json().get("deployments", [])
            if not deployments: return f"No deployments found for project '{project_name}'."
            details = [f"- **{d.get('state', 'N/A').upper()}**: {d.get('meta', {}).get('githubCommitMessage', 'N/A')} (Deployed on {datetime.fromtimestamp(d['createdAt'] / 1000).strftime('%Y-%m-%d %H:%M')})" for d in deployments]
            return f"Recent deployments for '{project_name}':\n" + "\n".join(details)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project '{project_name}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def get_project_details(self, project_name: str) -> str:
        """Gets detailed information about a single Vercel project."""
        try:
            response = self._make_request("GET", f"v9/projects/{project_name}")
            project = response.json()
            domains = [alias['domain'] for alias in project.get('alias', [])]
            details = [
                f"**Name**: {project.get('name')}", f"**ID**: `{project.get('id')}`",
                f"**Framework**: {project.get('framework', 'N/A')}",
                f"**Root Directory**: {project.get('rootDirectory', './') or './'}",
                f"**Domains**: " + (", ".join(domains) if domains else "None assigned."),
            ]
            return f"Details for project '{project_name}':\n" + "\n".join(details)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project '{project_name}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    # --- START: New Expanded Tools ---

    def create_project(
        self,
        name: str,
        framework: Optional[str] = None,
        root_directory: Optional[str] = None,
        git_provider: Optional[str] = None,
        git_repo_id: Optional[int] = None,
        git_repo_path: Optional[str] = None,
        production_branch: Optional[str] = None,
        build_command: Optional[str] = None,
        output_directory: Optional[str] = None,
        git_repository: Optional[Dict[str, Any]] = None,
        team_id: Optional[str] = None,
    ) -> str:
        """Creates a new Vercel project with optional Git and build configuration.

        Args:
            name: Project name in Vercel.
            framework: Optional framework identifier recognized by Vercel.
            root_directory: Path containing project sources.
            git_provider: Git provider slug ("github", "gitlab", "bitbucket"). Defaults to "github" when repo info is supplied.
            git_repo_id: Numeric repository ID (e.g., from GitHub API).
            git_repo_path: "owner/name" path for the repository.
            production_branch: Default production branch to deploy.
            build_command: Optional custom build command.
            output_directory: Optional directory containing build artifacts.
            git_repository: Full gitRepository dict; overrides individual git_* arguments when provided.
            team_id: Optional team scope.
        """
        if not name:
            return "Error: Project name is required."

        payload: Dict[str, Any] = {"name": name}
        if framework:
            payload["framework"] = framework
        if root_directory:
            payload["rootDirectory"] = root_directory
        if git_repository:
            payload["gitRepository"] = git_repository
        elif git_repo_id is not None and git_repo_path:
            provider = (git_provider or "github").lower()
            valid_providers = {"github", "gitlab", "bitbucket"}
            if provider not in valid_providers:
                return f"Error: Unsupported git provider '{provider}'. Choose from {sorted(valid_providers)}."

            repo_config: Dict[str, Any] = {
                "type": provider,
                "repoId": git_repo_id,
                "repoPath": git_repo_path,
            }
            if production_branch:
                repo_config["productionBranch"] = production_branch
            payload["gitRepository"] = repo_config
        elif any(value is not None for value in (git_provider, git_repo_id, git_repo_path, production_branch)):
            return "Error: git_repo_id and git_repo_path must both be provided to link a repository."
        if build_command:
            payload["buildCommand"] = build_command
        if output_directory:
            payload["outputDirectory"] = output_directory

        try:
            response = self._make_request("POST", "v9/projects", json_payload=payload, team_id=team_id)
            project = response.json()
            return f"Created project '{project.get('name', name)}' with ID `{project.get('id')}`."
        except requests.HTTPError as e:
            error_message = e.response.json().get('error', {}).get('message', 'Failed to create project.')
            if e.response.status_code == 409:
                return f"Error: Project with name '{name}' already exists."
            return f"API error: {error_message}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def delete_project(self, project_id_or_name: str, team_id: Optional[str] = None) -> str:
        """Deletes a Vercel project by its ID or name."""
        if not project_id_or_name:
            return "Error: Project identifier is required."

        try:
            self._make_request("DELETE", f"v9/projects/{project_id_or_name}", team_id=team_id)
            return f"Deleted project '{project_id_or_name}'."
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return f"Error: Project '{project_id_or_name}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to delete project.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def list_environment_variables(self, project_id_or_name: str) -> str:
        """
        Lists the environment variables for a specific Vercel project.
        This returns the ID, key, and target for each variable, but not the secret value.
        """
        try:
            response = self._make_request("GET", f"v9/projects/{project_id_or_name}/env")
            envs = response.json().get('envs', [])
            if not envs:
                return f"No environment variables found for project '{project_id_or_name}'."
            
            var_details = [f"- Key: **{env['key']}**, Target: {', '.join(env['target'])}, ID: `{env['id']}`" for env in envs]
            return f"Environment variables for '{project_id_or_name}':\n" + "\n".join(var_details)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project '{project_id_or_name}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def add_environment_variable(self, project_id_or_name: str, key: str, value: str, target: str) -> str:
        """
        Adds a new environment variable to a specified Vercel project.

        Args:
            project_id_or_name: The name or ID of the Vercel project.
            key: The name of the environment variable (e.g., 'DATABASE_URL').
            value: The secret value of the variable.
            target: The environment to apply it to. Must be one of: 'production', 'preview', 'development'.
        """
        valid_targets = ['production', 'preview', 'development']
        if target not in valid_targets:
            return f"Error: Invalid target '{target}'. Must be one of {valid_targets}."
        
        try:
            payload = {'key': key, 'value': value, 'type': 'secret', 'target': [target]}
            self._make_request("POST", f"v9/projects/{project_id_or_name}/env", json_payload=payload)
            return f"Successfully added environment variable '{key}' to project '{project_id_or_name}' for the '{target}' environment."
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project '{project_id_or_name}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to add variable.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def remove_environment_variable(self, project_id_or_name: str, env_id: str) -> str:
        """
        Removes an environment variable from a project using its unique ID.
        You must first call 'list_environment_variables' to get the ID for the variable you want to remove.
        """
        try:
            self._make_request("DELETE", f"v9/projects/{project_id_or_name}/env/{env_id}")
            return f"Successfully removed environment variable with ID '{env_id}' from project '{project_id_or_name}'."
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project or environment variable with ID '{env_id}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def trigger_redeployment(
        self,
        project_name: str,
        target: str = "production",
        team_id: Optional[str] = None,
    ) -> str:
        """
        Triggers a new deployment for a project using the latest available Git commit.
        This is useful for applying new environment variables or simply restarting the service.
        """
        valid_targets = {"production", "preview"}
        if target not in valid_targets:
            return f"Error: Invalid target '{target}'. Must be one of {sorted(valid_targets)}."

        try:
            payload = {"name": project_name, "target": target}
            response = self._make_request("POST", "v13/deployments", json_payload=payload, team_id=team_id)
            deployment_info = response.json()
            return f"Successfully triggered a new deployment for '{project_name}'. View status at: {deployment_info.get('url')}"
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project '{project_name}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to trigger deployment.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def create_deployment(
        self,
        project_name: str,
        git_provider: str = "github",
        branch: Optional[str] = None,
        commit_sha: Optional[str] = None,
        git_repo_id: Optional[int] = None,
        git_repo_path: Optional[str] = None,
        git_source: Optional[Dict[str, Any]] = None,
        target: str = "production",
        team_id: Optional[str] = None,
    ) -> str:
        """Creates a fresh deployment optionally pinned to a Git repository, branch, or commit."""
        valid_targets = {"production", "preview"}
        if target not in valid_targets:
            return f"Error: Invalid target '{target}'. Must be one of {sorted(valid_targets)}."

        payload: Dict[str, Any] = {"name": project_name, "target": target}

        if git_source is not None:
            payload["gitSource"] = git_source
        else:
            git_provider = (git_provider or "github").lower()
            using_git_source = any(
                value is not None
                for value in (git_repo_id, git_repo_path, branch, commit_sha)
            )

            if using_git_source:
                valid_providers = {"github", "gitlab", "bitbucket"}
                if git_provider not in valid_providers:
                    return f"Error: Unsupported git provider '{git_provider}'. Choose from {sorted(valid_providers)}."

                missing_fields = []
                if git_repo_id is None:
                    missing_fields.append("git_repo_id")
                if not git_repo_path:
                    missing_fields.append("git_repo_path")
                if missing_fields:
                    return (
                        "Error: "
                        + ", ".join(missing_fields)
                        + " must be provided to link a repository for deployment."
                    )

                git_source_payload: Dict[str, Any] = {
                    "type": git_provider,
                    "repoId": git_repo_id,
                    "repoPath": git_repo_path,
                }
                if branch:
                    git_source_payload["ref"] = branch
                if commit_sha:
                    git_source_payload["sha"] = commit_sha

                payload["gitSource"] = git_source_payload
            else:
                if branch or commit_sha:
                    return (
                        "Error: git_repo_id and git_repo_path must be provided when specifying "
                        "branch or commit_sha for deployment."
                    )

        try:
            response = self._make_request("POST", "v13/deployments", json_payload=payload, team_id=team_id)
            deployment_info = response.json()
            deployment_id = deployment_info.get("id")
            deployment_url = deployment_info.get("url")
            return "Successfully created deployment." + " " + " ".join(
                filter(
                    None,
                    [
                        f"Deployment ID: `{deployment_id}`." if deployment_id else None,
                        f"Status URL: {deployment_url}" if deployment_url else None,
                    ],
                )
            )
        except requests.HTTPError as e:
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to create deployment.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def cancel_deployment(self, deployment_id: str, team_id: Optional[str] = None) -> str:
        """Cancels an in-progress deployment."""
        try:
            self._make_request("POST", f"v13/deployments/{deployment_id}/cancel", team_id=team_id)
            return f"Deployment '{deployment_id}' has been cancelled."
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Deployment '{deployment_id}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to cancel deployment.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def get_deployment_status(self, deployment_id: str, team_id: Optional[str] = None) -> str:
        """Retrieves status details for a deployment."""
        try:
            response = self._make_request("GET", f"v13/deployments/{deployment_id}", team_id=team_id)
            deployment = response.json()
            details = [
                f"**State**: {deployment.get('state', 'unknown')}",
                f"**Ready State**: {deployment.get('readyState', 'unknown')}",
                f"**Inspector URL**: {deployment.get('inspectorUrl', 'N/A')}",
                f"**Created At**: {self._format_timestamp(deployment.get('createdAt'))}",
                f"**Ready At**: {self._format_timestamp(deployment.get('ready'))}",
            ]
            return "Deployment status:\n" + "\n".join(details)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Deployment '{deployment_id}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to retrieve deployment status.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def get_deployment_events(
        self,
        deployment_id: str,
        limit: int = 20,
        team_id: Optional[str] = None,
    ) -> str:
        """Retrieves recent events (build logs) for a deployment."""
        try:
            params = {"limit": limit}
            response = self._make_request(
                "GET",
                f"v13/deployments/{deployment_id}/events",
                params=params,
                team_id=team_id,
            )
            events = response.json().get("events", [])
            if not events:
                return f"No events found for deployment '{deployment_id}'."

            summaries = []
            for event in events:
                created = self._format_timestamp(event.get('createdAt'))
                message = event.get('payload', {}).get('message') or event.get('payload', {}).get('text') or "No message"
                summaries.append(f"- **{event.get('type', 'unknown')}** at {created}: {message}")

            return f"Events for deployment '{deployment_id}':\n" + "\n".join(summaries)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Deployment '{deployment_id}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to retrieve deployment events.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def list_deployment_checks(self, deployment_id: str, team_id: Optional[str] = None) -> str:
        """Lists checks associated with a deployment."""
        try:
            response = self._make_request("GET", f"v13/deployments/{deployment_id}/checks", team_id=team_id)
            checks = response.json().get("checks", [])
            if not checks:
                return f"No checks found for deployment '{deployment_id}'."

            summaries = [
                f"- **{check.get('name', 'Unnamed')}** (ID: `{check.get('id')}`) — Status: {check.get('status', 'unknown')}"
                for check in checks
            ]
            return f"Checks for deployment '{deployment_id}':\n" + "\n".join(summaries)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Deployment '{deployment_id}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to list deployment checks.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def create_deployment_check(
        self,
        deployment_id: str,
        name: str,
        status: str,
        conclusion: Optional[str] = None,
        details_url: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> str:
        """Creates a deployment check, useful for custom CI validations."""
        payload: Dict[str, Any] = {"name": name, "status": status}
        if conclusion:
            payload["conclusion"] = conclusion
        if details_url:
            payload["detailsUrl"] = details_url

        try:
            response = self._make_request(
                "POST",
                f"v13/deployments/{deployment_id}/checks",
                json_payload=payload,
                team_id=team_id,
            )
            check = response.json()
            check_id = check.get("id") if isinstance(check, dict) else None
            return (
                f"Created deployment check '{check.get('name', name)}' with ID `{check_id}`."
                if check_id
                else "Deployment check created."
            )
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Deployment '{deployment_id}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to create deployment check.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def update_deployment_check(
        self,
        check_id: str,
        status: str,
        conclusion: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> str:
        """Updates the status or conclusion of a deployment check."""
        payload: Dict[str, Any] = {"status": status}
        if conclusion:
            payload["conclusion"] = conclusion

        try:
            response = self._make_request(
                "PATCH",
                f"v13/deployment-checks/{check_id}",
                json_payload=payload,
                team_id=team_id,
            )
            updated = response.json()
            return f"Updated deployment check `{check_id}`: Status {updated.get('status', status)}."
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Deployment check '{check_id}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to update deployment check.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def update_project_settings(
        self,
        project_id_or_name: str,
        settings: Dict[str, Any],
        team_id: Optional[str] = None,
    ) -> str:
        """Updates configuration values on a Vercel project."""
        if not settings:
            return "Error: 'settings' cannot be empty."

        try:
            response = self._make_request(
                "PATCH",
                f"v9/projects/{project_id_or_name}",
                json_payload=settings,
                team_id=team_id,
            )
            project = response.json()
            return f"Updated project '{project.get('name', project_id_or_name)}' successfully."
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return f"Error: Project '{project_id_or_name}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to update project settings.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def list_project_domains(self, project_id_or_name: str, team_id: Optional[str] = None) -> str:
        """
        Lists all domains assigned to a specific Vercel project, including automatic and custom domains.
        """
        try:
            response = self._make_request("GET", f"v9/projects/{project_id_or_name}/domains", team_id=team_id)
            domains = response.json().get('domains', [])
            if not domains:
                return f"No domains are configured for project '{project_id_or_name}'."
            
            domain_details = [f"- **{d['name']}** ({'Verified' if d['verified'] else 'Not Verified'})" for d in domains]
            return f"Domains for '{project_id_or_name}':\n" + "\n".join(domain_details)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project '{project_id_or_name}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def add_project_domain(
        self,
        project_id_or_name: str,
        domain: str,
        team_id: Optional[str] = None,
    ) -> str:
        """Assigns a domain to the given project."""
        if not domain:
            return "Error: Domain must be provided."

        try:
            payload = {"name": domain}
            response = self._make_request(
                "POST",
                f"v9/projects/{project_id_or_name}/domains",
                json_payload=payload,
                team_id=team_id,
            )
            domain_info = response.json()
            return f"Added domain '{domain_info.get('name', domain)}' to project '{project_id_or_name}'."
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return f"Error: Project '{project_id_or_name}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to add domain.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def remove_project_domain(
        self,
        project_id_or_name: str,
        domain: str,
        team_id: Optional[str] = None,
    ) -> str:
        """Removes a domain from the given project."""
        if not domain:
            return "Error: Domain must be provided."

        try:
            self._make_request(
                "DELETE",
                f"v9/projects/{project_id_or_name}/domains/{domain}",
                team_id=team_id,
            )
            return f"Removed domain '{domain}' from project '{project_id_or_name}'."
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return f"Error: Project '{project_id_or_name}' or domain '{domain}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to remove domain.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def verify_project_domain(
        self,
        project_id_or_name: str,
        domain: str,
        team_id: Optional[str] = None,
    ) -> str:
        """Requests verification of a project domain."""
        if not domain:
            return "Error: Domain must be provided."

        try:
            self._make_request(
                "POST",
                f"v9/projects/{project_id_or_name}/domains/{domain}/verify",
                team_id=team_id,
            )
            return f"Verification requested for domain '{domain}' on project '{project_id_or_name}'."
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return f"Error: Project '{project_id_or_name}' or domain '{domain}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to verify domain.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def list_global_environment_variables(self, team_id: Optional[str] = None) -> str:
        """Lists account-level environment variables available to projects."""
        try:
            response = self._make_request("GET", "v9/projects/env", team_id=team_id)
            envs = response.json().get("envs", [])
            if not envs:
                return "No global environment variables found."

            summaries = [
                f"- Key: **{env.get('key')}**, Target: {', '.join(env.get('target', []))}, ID: `{env.get('id')}`"
                for env in envs
            ]
            return "Global environment variables:\n" + "\n".join(summaries)
        except requests.HTTPError as e:
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to list global environment variables.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def add_global_environment_variable(
        self,
        key: str,
        value: str,
        targets: List[str],
        team_id: Optional[str] = None,
    ) -> str:
        """Creates a new account-level environment variable."""
        if not key or not value:
            return "Error: Both key and value must be provided."
        if not targets:
            return "Error: At least one target must be specified."

        payload = {"key": key, "value": value, "target": targets, "type": "secret"}

        try:
            response = self._make_request(
                "POST",
                "v9/projects/env",
                json_payload=payload,
                team_id=team_id,
            )
            env = response.json()
            return f"Added global environment variable '{env.get('key', key)}' with ID `{env.get('id')}`."
        except requests.HTTPError as e:
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to add global environment variable.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def remove_global_environment_variable(self, env_id: str, team_id: Optional[str] = None) -> str:
        """Deletes an account-level environment variable."""
        if not env_id:
            return "Error: Environment variable ID must be provided."

        try:
            self._make_request("DELETE", f"v9/projects/env/{env_id}", team_id=team_id)
            return f"Removed global environment variable with ID '{env_id}'."
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return f"Error: Environment variable '{env_id}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to remove global environment variable.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def get_integration_configuration(self, configuration_id: str) -> str:
        """Fetches metadata about the integration installation."""
        if not configuration_id:
            return "Error: configuration_id is required."

        try:
            response = self._make_request("GET", f"v1/integration-configurations/{configuration_id}")
            config = response.json()
            details = [
                f"**Configuration ID**: `{config.get('id')}`",
                f"**Name**: {config.get('name', 'N/A')}",
                f"**Created At**: {config.get('createdAt', 'N/A')}",
                f"**Scopes**: {', '.join(config.get('scopes', [])) or 'N/A'}",
            ]
            return "Integration configuration details:\n" + "\n".join(details)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return f"Error: Integration configuration '{configuration_id}' not found."
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to fetch integration configuration.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def list_teams(self) -> str:
        """Lists teams accessible to the authenticated user."""
        try:
            response = self._make_request("GET", "v2/teams")
            teams = response.json().get("teams", [])
            if not teams:
                return "No teams found for this account."

            summaries = [f"- **{team.get('name')}** (ID: `{team.get('id')}`)" for team in teams]
            return "Available teams:\n" + "\n".join(summaries)
        except requests.HTTPError as e:
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to list teams.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def get_current_user(self) -> str:
        """Retrieves the authenticated user's profile details."""
        try:
            response = self._make_request("GET", "v2/user")
            user = response.json().get("user", {})
            details = [
                f"**Name**: {user.get('name', 'N/A')}",
                f"**Email**: {user.get('email', 'N/A')}",
                f"**User ID**: `{user.get('id', 'N/A')}`",
                f"**Username**: {user.get('username', 'N/A')}",
            ]
            return "Current user details:\n" + "\n".join(details)
        except requests.HTTPError as e:
            return f"API error: {e.response.json().get('error', {}).get('message', 'Failed to fetch current user.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    # --- END: New Expanded Tools ---
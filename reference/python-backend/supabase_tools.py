# python-backend/supabase_tools.py

import logging
import requests
from typing import Optional, Dict, Any, List

from agno.tools import Toolkit
from supabase_client import supabase_client

logger = logging.getLogger(__name__)

class SupabaseTools(Toolkit):
    """
    A comprehensive toolkit for interacting with the Supabase Management API.
    It allows the agent to manage projects, edge functions, secrets, and storage buckets.
    """

    def __init__(self, user_id: str):
        """Initializes the SupabaseTools toolkit."""
        super().__init__(
            name="supabase_tools",
            tools=[
                # Core Read Tools
                self.list_organizations,
                self.list_projects,
                self.get_project_details,
                # Project Management Tools
                self.pause_project,
                self.restore_project,
                # New Expanded Tools
                self.list_edge_functions,
                self.list_secrets,
                self.list_storage_buckets,
                self.create_storage_bucket,
                self.delete_storage_bucket,
            ],
        )
        self.user_id = user_id
        self._access_token: Optional[str] = None
        self._token_fetched = False
        self.api_base_url = "https://api.supabase.com/v1"

    def _get_access_token(self) -> Optional[str]:
        """Retrieves the user's Supabase Management API access token from the database."""
        if self._token_fetched:
            return self._access_token
        try:
            response = (
                supabase_client.from_("user_integrations")
                .select("access_token").eq("user_id", self.user_id).eq("service", "supabase")
                .single().execute()
            )
            self._access_token = response.data.get("access_token") if response.data else None
        except Exception as e:
            logger.error(f"Error fetching Supabase token for user {self.user_id}: {e}")
            self._access_token = None
        self._token_fetched = True
        return self._access_token

    def _make_request(self, method: str, endpoint: str, json_payload: Optional[Dict[str, Any]] = None) -> requests.Response:
        """A helper function to make authenticated requests to the Supabase Management API."""
        token = self._get_access_token()
        if not token:
            raise Exception("Supabase account not connected or token is invalid.")
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"{self.api_base_url}/{endpoint}"
        
        response = requests.request(method, url, headers=headers, json=json_payload)
        response.raise_for_status()
        return response

    # --- Core Read Tools ---

    def list_organizations(self) -> str:
        """Lists all organizations the connected Supabase user is a member of."""
        try:
            response = self._make_request("GET", "organizations")
            organizations = response.json()
            if not organizations: return "No Supabase organizations were found for your account."
            summaries = [f"- **{org['name']}** (ID: `{org['id']}`)" for org in organizations]
            return "Here are your Supabase organizations:\n" + "\n".join(summaries)
        except Exception as e:
            return f"An error occurred: {e}"

    def list_projects(self) -> str:
        """Lists all Supabase projects the connected user has access to."""
        try:
            response = self._make_request("GET", "projects")
            projects = response.json()
            if not projects: return "No Supabase projects were found for your account."
            details = [f"- **{p['name']}** (Ref: `{p['id']}`, Region: {p['region']})" for p in projects]
            return "Here are your Supabase projects:\n" + "\n".join(details)
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def get_project_details(self, project_ref: str) -> str:
        """Gets detailed information for a specific Supabase project using its reference ID."""
        try:
            response = self._make_request("GET", f"projects/{project_ref}")
            project = response.json()
            details = [
                f"**Name**: {project.get('name')}",
                f"**ID/Ref**: `{project.get('id')}`",
                f"**Region**: {project.get('region')}",
                f"**Database Host**: {project.get('database', {}).get('host')}",
                f"**Postgres Version**: {project.get('database', {}).get('version')}",
            ]
            return f"Details for project '{project.get('name')}':\n" + "\n".join(details)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project with ref '{project_ref}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    # --- Project Management Tools ---

    def pause_project(self, project_ref: str) -> str:
        """Pauses a Supabase project. This will disable the database and APIs."""
        try:
            response = self._make_request("POST", f"projects/{project_ref}/pause")
            project_name = response.json().get('name', project_ref)
            return f"Successfully initiated pausing for project '{project_name}'. It may take a few moments to complete."
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project with ref '{project_ref}' not found."
            return f"API error: {e.response.json().get('error', 'Failed to pause project.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def restore_project(self, project_ref: str) -> str:
        """Restores a paused Supabase project, enabling its database and APIs."""
        try:
            response = self._make_request("POST", f"projects/{project_ref}/restore")
            project_name = response.json().get('name', project_ref)
            return f"Successfully initiated restoration for project '{project_name}'. It may take a few moments to become fully active."
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project with ref '{project_ref}' not found."
            return f"API error: {e.response.json().get('error', 'Failed to restore project.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    # --- New Expanded Tools ---

    def list_edge_functions(self, project_ref: str) -> str:
        """Lists all serverless Edge Functions for a specific project."""
        try:
            response = self._make_request("GET", f"projects/{project_ref}/functions")
            functions = response.json()
            if not functions: return f"No Edge Functions found for project '{project_ref}'."
            details = [f"- **{f['name']}** (Slug: `{f['slug']}`, Status: {f['status']})" for f in functions]
            return f"Edge Functions for project '{project_ref}':\n" + "\n".join(details)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project with ref '{project_ref}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def list_secrets(self, project_ref: str) -> str:
        """Lists the names of all secrets (environment variables) for a specific project. Values are not returned for security."""
        try:
            response = self._make_request("GET", f"projects/{project_ref}/secrets")
            secrets = response.json()
            if not secrets: return f"No secrets found for project '{project_ref}'."
            secret_names = [f"- {s['name']}" for s in secrets]
            return f"Secrets for project '{project_ref}':\n" + "\n".join(secret_names)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project with ref '{project_ref}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def list_storage_buckets(self, project_ref: str) -> str:
        """Lists all storage buckets for a specific project."""
        try:
            # Note: This endpoint is slightly different from the others.
            response = self._make_request("GET", f"projects/{project_ref}/storage/buckets")
            buckets = response.json()
            if not buckets: return f"No storage buckets found for project '{project_ref}'."
            details = [f"- **{b['name']}** (ID: `{b['id']}`, Public: {b['public']})" for b in buckets]
            return f"Storage buckets for project '{project_ref}':\n" + "\n".join(details)
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project with ref '{project_ref}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def create_storage_bucket(self, project_ref: str, bucket_name: str, is_public: bool = False) -> str:
        """Creates a new storage bucket in a project."""
        try:
            payload = {'name': bucket_name, 'public': is_public}
            response = self._make_request("POST", f"projects/{project_ref}/storage/buckets", json_payload=payload)
            bucket_id = response.json().get('id')
            return f"Successfully created storage bucket '{bucket_name}' with ID: `{bucket_id}`."
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project with ref '{project_ref}' not found."
            return f"API error: {e.response.json().get('error', 'Failed to create bucket.')}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def delete_storage_bucket(self, project_ref: str, bucket_id: str) -> str:
        """Deletes a storage bucket from a project using its ID."""
        try:
            self._make_request("DELETE", f"projects/{project_ref}/storage/buckets/{bucket_id}")
            return f"Successfully deleted storage bucket with ID '{bucket_id}'."
        except requests.HTTPError as e:
            if e.response.status_code == 404: return f"Error: Project with ref '{project_ref}' or bucket with ID '{bucket_id}' not found."
            return f"API error: {e}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"
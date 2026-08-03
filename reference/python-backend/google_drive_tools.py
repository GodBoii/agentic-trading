# python-backend/google_drive_tools.py (Expanded Version)

import io
import logging
import os
from typing import Optional, List

from agno.tools import Toolkit
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from supabase_client import supabase_client

logger = logging.getLogger(__name__)

class GoogleDriveTools(Toolkit):
    """A toolkit for searching, reading, creating, and managing files in Google Drive."""

    def __init__(self, user_id: str):
        super().__init__(
            name="google_drive_tools",
            tools=[
                self.search_files,
                self.read_file_content,
                self.create_file,
                self.manage_file,
                self.share_file,
            ],
        )
        self.user_id = user_id
        self._credentials: Optional[Credentials] = None
        self._drive_service: Optional[Resource] = None

    def _get_credentials(self) -> Optional[Credentials]:
        # This method is unchanged and remains the same.
        if self._credentials and self._credentials.valid:
            return self._credentials
        try:
            response = (
                supabase_client.from_("user_integrations")
                .select("access_token, refresh_token, scopes")
                .eq("user_id", self.user_id).eq("service", "google")
                .single().execute()
            )
            if not response.data: return None
            creds_data = response.data
            creds = Credentials(
                token=creds_data.get('access_token'),
                refresh_token=creds_data.get('refresh_token'),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                scopes=creds_data.get('scopes')
            )
            if creds.expired:
                if creds.refresh_token:
                    creds.refresh(Request())
                    supabase_client.from_('user_integrations').update({
                        'access_token': creds.token,
                        'scopes': creds.scopes
                    }).eq('user_id', self.user_id).eq('service', 'google').execute()
                else:
                    return None
            self._credentials = creds
            return self._credentials
        except Exception as e:
            logger.error(f"Error fetching/refreshing Google credentials for user {self.user_id}: {e}", exc_info=True)
            return None

    def _get_drive_service(self) -> Optional[Resource]:
        # This method is unchanged and remains the same.
        if self._drive_service: return self._drive_service
        credentials = self._get_credentials()
        if not credentials: return None
        try:
            service = build('drive', 'v3', credentials=credentials)
            self._drive_service = service
            return self._drive_service
        except HttpError as error:
            logger.error(f"An error occurred building the Google Drive service: {error}")
            return None

    # --- EXISTING TOOLS (Unchanged) ---
    def search_files(self, query: str, max_results: int = 10) -> str:
        # This method is unchanged.
        service = self._get_drive_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            search_query = f"name contains '{query}' or fullText contains '{query}'"
            results = service.files().list(
                q=search_query, pageSize=max_results, fields="nextPageToken, files(id, name, mimeType)"
            ).execute()
            items = results.get('files', [])
            if not items: return f"No files found matching the query: '{query}'"
            file_summaries = [f"Name: {item['name']}\nType: {item['mimeType']}\nFile ID: {item['id']}\n---" for item in items]
            return "\n".join(file_summaries)
        except HttpError as error:
            return f"An error occurred while searching your Google Drive: {error}"

    def read_file_content(self, file_id: str) -> str:
        # This method is unchanged.
        service = self._get_drive_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
            mime_type = file_metadata.get('mimeType')
            request = None
            if mime_type == 'application/vnd.google-apps.document':
                request = service.files().export_media(fileId=file_id, mimeType='text/plain')
            elif mime_type and mime_type.startswith('text/'):
                request = service.files().get_media(fileId=file_id)
            else:
                return f"Cannot read content from this file type: {mime_type}."
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            return fh.getvalue().decode('utf-8')
        except HttpError as error:
            return f"An error occurred while reading the file: {error}"

    # --- NEW EXPANDED TOOLS ---
    def create_file(self, name: str, folder_id: Optional[str] = None, mime_type: str = 'application/vnd.google-apps.document') -> str:
        """
        Creates a new, empty file in Google Drive, such as a Google Doc or a plain text file.

        Args:
            name: The name of the new file.
            folder_id: Optional. The ID of the folder to create the file in.
            mime_type: The MIME type of the file. Defaults to a Google Doc. Use 'text/plain' for a text file.

        Returns:
            A confirmation message with the new file's ID and link.
        """
        service = self._get_drive_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            file_metadata = {'name': name, 'mimeType': mime_type}
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            file = service.files().create(body=file_metadata, fields='id, webViewLink').execute()
            return f"Successfully created file '{name}'. ID: {file.get('id')}, Link: {file.get('webViewLink')}"
        except HttpError as error:
            return f"An error occurred creating the file: {error}"

    def manage_file(self, file_id: str, new_name: Optional[str] = None, add_parent_folder_id: Optional[str] = None, remove_parent_folder_id: Optional[str] = None) -> str:
        """
        Manages a file by renaming it or moving it to a different folder.

        Args:
            file_id: The ID of the file to manage.
            new_name: Optional. The new name for the file.
            add_parent_folder_id: Optional. The ID of the folder to move the file into.
            remove_parent_folder_id: Optional. The ID of the folder to move the file out of.

        Returns:
            A confirmation message.
        """
        service = self._get_drive_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            file_update_body = {}
            if new_name:
                file_update_body['name'] = new_name
            
            # To move a file, you need to specify which folder to add it to and which to remove it from.
            file = service.files().update(
                fileId=file_id,
                body=file_update_body,
                addParents=add_parent_folder_id,
                removeParents=remove_parent_folder_id,
                fields='id, name, parents'
            ).execute()
            return f"Successfully updated file '{file.get('name')}'."
        except HttpError as error:
            return f"An error occurred managing the file: {error}"

    def share_file(self, file_id: str, email_address: str, role: str = 'reader') -> str:
        """
        Shares a file with another user by their email address.

        Args:
            file_id: The ID of the file to share.
            email_address: The email address of the user to share with.
            role: The role to grant. Can be 'reader', 'commenter', or 'writer'.

        Returns:
            A confirmation message.
        """
        service = self._get_drive_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            permission_body = {'type': 'user', 'role': role, 'emailAddress': email_address}
            service.permissions().create(
                fileId=file_id,
                body=permission_body,
                sendNotificationEmail=True
            ).execute()
            return f"Successfully shared file with {email_address} as a {role}."
        except HttpError as error:
            return f"An error occurred sharing the file: {error}"
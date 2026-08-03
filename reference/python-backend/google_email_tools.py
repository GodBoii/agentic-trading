# python-backend/google_email_tools.py (Expanded Version)

import base64
import logging
import os
from email.mime.text import MIMEText
from typing import List, Optional

from agno.tools import Toolkit
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from supabase_client import supabase_client

logger = logging.getLogger(__name__)

class GoogleEmailTools(Toolkit):
    """A toolkit for reading, searching, sending, and managing emails via the Gmail API."""

    def __init__(self, user_id: str):
        super().__init__(
            name="google_email_tools",
            tools=[
                self.read_latest_emails,
                self.send_email,
                self.search_emails,
                self.reply_to_email,
                self.modify_email,
            ],
        )
        self.user_id = user_id
        self._credentials: Optional[Credentials] = None
        self._gmail_service: Optional[Resource] = None

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
                        'access_token': creds.token
                    }).eq('user_id', self.user_id).eq('service', 'google').execute()
                else:
                    return None
            self._credentials = creds
            return self._credentials
        except Exception as e:
            logger.error(f"Error fetching/refreshing Google credentials for user {self.user_id}: {e}", exc_info=True)
            return None

    def _get_gmail_service(self) -> Optional[Resource]:
        # This method is unchanged and remains the same.
        if self._gmail_service: return self._gmail_service
        credentials = self._get_credentials()
        if not credentials: return None
        try:
            service = build('gmail', 'v1', credentials=credentials)
            self._gmail_service = service
            return self._gmail_service
        except HttpError as error:
            logger.error(f"An error occurred building the Gmail service: {error}")
            return None

    # --- EXISTING TOOLS (Unchanged) ---
    def read_latest_emails(self, max_results: int = 5, only_unread: bool = True) -> str:
        # This method is unchanged.
        service = self._get_gmail_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            query = 'is:unread' if only_unread else ''
            results = service.users().messages().list(userId='me', maxResults=max_results, q=query).execute()
            messages = results.get('messages', [])
            if not messages: return "No new emails found."
            email_summaries = []
            for msg in messages:
                msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
                headers = msg_data['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
                snippet = msg_data['snippet']
                email_summaries.append(f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}\n---")
            return "\n".join(email_summaries)
        except HttpError as error:
            return f"An error occurred while trying to read your emails: {error}"

    def send_email(self, to: str, subject: str, body: str) -> str:
        # This method is unchanged.
        service = self._get_gmail_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            create_message = {'raw': encoded_message}
            send_message = service.users().messages().send(userId="me", body=create_message).execute()
            return f"Email sent successfully to {to}. Message ID: {send_message['id']}"
        except HttpError as error:
            return f"An error occurred while trying to send the email: {error}"

    # --- NEW EXPANDED TOOLS ---
    def search_emails(self, query: str, max_results: int = 10) -> str:
        """
        Searches the user's entire Gmail inbox using a specific query.
        Supports standard Gmail search operators like 'from:', 'to:', 'subject:', 'is:unread'.

        Args:
            query: The search query.
            max_results: The maximum number of emails to return.

        Returns:
            A formatted string of matching emails with their ID, sender, and subject.
        """
        service = self._get_gmail_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            results = service.users().messages().list(userId='me', maxResults=max_results, q=query).execute()
            messages = results.get('messages', [])
            if not messages: return f"No emails found matching query: '{query}'"
            
            email_details = []
            for msg in messages:
                msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['Subject', 'From']).execute()
                headers = msg_data['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
                email_details.append(f"From: {sender}\nSubject: {subject}\nMessage ID: {msg['id']}\n---")
            return "\n".join(email_details)
        except HttpError as error:
            return f"An error occurred while searching emails: {error}"

    def reply_to_email(self, message_id: str, body: str) -> str:
        """
        Sends a reply to a specific email, keeping it in the same conversation thread.

        Args:
            message_id: The ID of the email to reply to.
            body: The plain text content of the reply.

        Returns:
            A confirmation message or an error message.
        """
        service = self._get_gmail_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            original_message = service.users().messages().get(userId='me', id=message_id, format='metadata', metadataHeaders=['Subject', 'From', 'To', 'Cc', 'Message-ID', 'References']).execute()
            headers = original_message['payload']['headers']
            
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
            reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
            
            original_message_id_header = next((h['value'] for h in headers if h['name'].lower() == 'message-id'), None)
            references_header = next((h['value'] for h in headers if h['name'].lower() == 'references'), original_message_id_header)
            
            reply_to = next((h['value'] for h in headers if h['name'].lower() == 'from'), None)

            message = MIMEText(body)
            message['to'] = reply_to
            message['subject'] = reply_subject
            if original_message_id_header:
                message['In-Reply-To'] = original_message_id_header
            if references_header:
                message['References'] = references_header

            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            create_message = {'raw': encoded_message, 'threadId': original_message['threadId']}
            
            sent_message = service.users().messages().send(userId="me", body=create_message).execute()
            return f"Reply sent successfully to {reply_to}. Message ID: {sent_message['id']}"
        except HttpError as error:
            return f"An error occurred while replying to the email: {error}"

    def modify_email(self, message_id: str, add_labels: List[str] = None, remove_labels: List[str] = None) -> str:
        """
        Modifies an email by adding or removing labels (e.g., 'UNREAD', 'TRASH', 'STARRED').

        Args:
            message_id: The ID of the email to modify.
            add_labels: A list of label IDs to add (e.g., ['UNREAD', 'STARRED']).
            remove_labels: A list of label IDs to remove (e.g., ['INBOX'] to archive).

        Returns:
            A confirmation message or an error message.
        """
        service = self._get_gmail_service()
        if not service: return "Google account not connected or credentials invalid."
        try:
            modify_body = {'addLabelIds': add_labels or [], 'removeLabelIds': remove_labels or []}
            service.users().messages().modify(userId='me', id=message_id, body=modify_body).execute()
            return f"Email with ID {message_id} was modified successfully."
        except HttpError as error:
            return f"An error occurred while modifying the email: {error}"
# python-backend/browser_tools.py (Updated for Redis Pub/Sub)

import logging
import uuid
import json
import time
from typing import Dict, Any, Literal, Union

from redis import Redis

from agno.media import Image
from agno.tools import Toolkit
from agno.tools.function import ToolResult
from supabase_client import supabase_client

BROWSER_COMMAND_TIMEOUT_SECONDS = 120

logger = logging.getLogger(__name__)

class BrowserTools(Toolkit):
    """
    A scalable, distributed toolkit that acts as a server-side proxy for
    controlling a client-side browser. It uses Redis Pub/Sub for asynchronous
    request/response handling, making it safe for multi-worker environments.
    """

    def __init__(self, sid: str, socketio, redis_client: Redis, **kwargs):
        """
        Initializes the BrowserTools toolkit.

        Args:
            sid (str): The unique Socket.IO session ID for the connected client.
            socketio: The main Flask-SocketIO server instance.
            redis_client (Redis): An initialized Redis client for Pub/Sub.
        """
        self.sid = sid
        self.socketio = socketio
        self.redis_client = redis_client

        super().__init__(
            name="browser_tools",
            tools=[
                self.get_browser_status, self.navigate, self.get_current_view,
                self.click, self.type_text, self.scroll, self.go_back,
                self.go_forward, self.list_tabs, self.open_new_tab,
                self.switch_to_tab, self.close_tab, self.hover_over_element,
                self.select_dropdown_option, self.handle_alert, self.press_key,
                self.extract_text_from_element, self.get_element_attributes,
                self.extract_table_data, self.refresh_page,
                self.wait_for_element, self.manage_cookies,
                self.focus_element, self.click_by_text, self.click_coordinates,
            ],
        )

    def _process_view_result(self, result: Dict[str, Any]) -> ToolResult:
        if result.get("status") == "success" and "screenshot_path" in result:
            screenshot_path = result.pop("screenshot_path")
            try:
                image_bytes = supabase_client.storage.from_('media-uploads').download(screenshot_path)
                image_artifact = Image(content=image_bytes)
                return ToolResult(content=json.dumps(result), images=[image_artifact])
            except Exception as e:
                logger.error(f"Supabase screenshot download failed: {e}")
                result["error"] = f"Error: Could not retrieve screenshot from path {screenshot_path}."
                return ToolResult(content=json.dumps(result))
        
        return ToolResult(content=json.dumps(result))

    def _send_command_and_wait(self, command_payload: Dict[str, Any]) -> Union[Dict[str, Any], ToolResult]:
        """
        Sends a command to the client via SocketIO and waits for the response
        on a unique Redis Pub/Sub channel. This is a non-blocking, scalable pattern.
        """
        request_id = str(uuid.uuid4())
        command_payload['request_id'] = request_id
        action = command_payload.get('action', 'unknown')

        response_channel = f"browser-response:{request_id}"
        pubsub = self.redis_client.pubsub()
        timeout_seconds = BROWSER_COMMAND_TIMEOUT_SECONDS
        if action == 'wait_for_element':
            timeout_seconds = max(timeout_seconds, int(command_payload.get('timeout', 10)) + 20)

        try:
            pubsub.subscribe(response_channel)
            
            # 1. Send the command to the client
            self.socketio.emit('browser-command', command_payload, room=self.sid)
            deadline = time.monotonic() + timeout_seconds

            # 2. Wait for a message on the subscribed channel
            while time.monotonic() < deadline:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    continue

                try:
                    result = json.loads(message['data'])
                except Exception as decode_error:
                    logger.error("Browser result decode failed for action '%s': %s", action, decode_error)
                    return ToolResult(content=json.dumps({
                        "status": "error",
                        "error": f"Invalid browser response payload for action '{action}'."
                    }))

                if "screenshot_path" in result:
                    return self._process_view_result(result)

                return ToolResult(content=json.dumps(result))

            logger.error(
                "Browser command timed out after %ss (action=%s, request_id=%s, sid=%s)",
                timeout_seconds,
                action,
                request_id,
                self.sid
            )
            return ToolResult(content=json.dumps({
                "status": "error",
                "error": f"Browser command '{action}' timed out after {timeout_seconds} seconds."
            }))

        except Exception as e:
            logger.error(f"Browser command error: {e}")
            return ToolResult(content=json.dumps({
                "status": "error",
                "error": f"An internal error occurred while waiting for the browser: {e}"
            }))
        finally:
            # 3. Always clean up the subscription
            pubsub.unsubscribe(response_channel)
            pubsub.close()

    # --- Public Tool Methods ---
    # The function signatures remain the same. Their implementation via
    # _send_command_and_wait is now scalable.
    
    def get_browser_status(self) -> Dict[str, Any]:
        """
        Check browser connection status and launch browser if needed.
        
        This is the FIRST tool you must call before any other browser action.
        It will automatically launch Chrome and establish a connection if needed.
        
        Returns:
            Dict with status='connected' if browser is ready, or status='disconnected' with error details.
        """
        return self._send_command_and_wait({'action': 'status'})

    def navigate(self, url: str) -> Union[Dict[str, Any], ToolResult]:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        return self._send_command_and_wait({'action': 'navigate', 'url': url})

    def get_current_view(self) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'get_view'})

    def click(self, element_id: int, description: str = "") -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({
            'action': 'click',
            'element_id': element_id,
            'description': description
        })

    def type_text(
        self,
        element_id: int,
        text: str,
        description: str = "",
        clear_existing: bool = True
    ) -> Union[Dict[str, Any], ToolResult]:
        """
        Type text into an element. Handles both standard inputs AND contenteditable 
        elements (like reply/compose boxes in Slack, Gmail, Discord, Teams, etc.).
        
        The tool automatically detects the element type and uses the appropriate strategy:
        - For <input>/<textarea>: clears via value reset + types via DOM
        - For contenteditable/[role="textbox"]: clicks to focus, Ctrl+A to select, 
          then types character-by-character with real key events
        
        Args:
            element_id: The element ID from get_current_view()
            text: The text to type
            description: Optional description of the target element
            clear_existing: Whether to clear existing content first (default True)
        
        Tips for reply/compose boxes:
        1. First call focus_element(element_id) to activate the reply box
        2. Then call type_text(element_id, "your message")
        3. Then call press_key("Enter") or press_key("Control+Enter") to send
        """
        return self._send_command_and_wait({
            'action': 'type',
            'element_id': element_id,
            'text': text,
            'description': description,
            'clear_existing': clear_existing
        })

    def scroll(self, direction: Literal['up', 'down']) -> Union[Dict[str, Any], ToolResult]:
        if direction not in ['up', 'down']:
            return {"status": "error", "error": "Invalid scroll direction. Must be 'up' or 'down'."}
        return self._send_command_and_wait({'action': 'scroll', 'direction': direction})

    # ... (The rest of the tool methods: go_back, go_forward, etc., are unchanged) ...
    def go_back(self) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'go_back'})

    def go_forward(self) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'go_forward'})

    def list_tabs(self) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'list_tabs'})

    def open_new_tab(self, url: str) -> Union[Dict[str, Any], ToolResult]:
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        return self._send_command_and_wait({'action': 'open_new_tab', 'url': url})

    def switch_to_tab(self, tab_index: int) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'switch_to_tab', 'tab_index': tab_index})

    def close_tab(self, tab_index: int) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'close_tab', 'tab_index': tab_index})

    def hover_over_element(self, element_id: int) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'hover', 'element_id': element_id})

    def select_dropdown_option(self, element_id: int, value: str) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'select_option', 'element_id': element_id, 'value': value})

    def handle_alert(self, action: Literal['accept', 'dismiss']) -> Dict[str, Any]:
        if action not in ['accept', 'dismiss']:
            return {"status": "error", "error": "Invalid alert action. Must be 'accept' or 'dismiss'."}
        return self._send_command_and_wait({'action': 'handle_alert', 'alert_action': action})

    def press_key(self, key: str) -> Union[Dict[str, Any], ToolResult]:
        """
        Press a keyboard key or key combination in the browser.
        
        Args:
            key: Key to press. Can be a single key or a combination with '+'.
            
            Single keys: Enter, Escape, Tab, ArrowDown, ArrowUp, ArrowLeft, 
                         ArrowRight, Backspace, Delete, Space, Home, End, 
                         PageUp, PageDown, F1-F12
            
            Combinations (use '+' separator):
                - Control+Enter  (send message in most chat apps)
                - Control+a      (select all text)
                - Shift+Enter    (new line without sending)
                - Control+Shift+Enter
                - Alt+Enter
        
        Example: press_key("Control+Enter") to send a message in Slack/Teams/Gmail
        """
        return self._send_command_and_wait({'action': 'press_key', 'key': key})

    def extract_text_from_element(self, element_id: int) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'extract_text', 'element_id': element_id})

    def get_element_attributes(self, element_id: int) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'get_attributes', 'element_id': element_id})

    def extract_table_data(self, element_id: int) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'extract_table', 'element_id': element_id})

    def refresh_page(self) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'refresh'})

    def wait_for_element(self, selector: str, timeout: int = 10) -> Union[Dict[str, Any], ToolResult]:
        return self._send_command_and_wait({'action': 'wait_for_element', 'selector': selector, 'timeout': timeout})

    def manage_cookies(self, action: Literal['accept_all', 'clear_all']) -> Union[Dict[str, Any], ToolResult]:
        if action not in ['accept_all', 'clear_all']:
            return {"status": "error", "error": "Invalid cookie action. Must be 'accept_all' or 'clear_all'."}
        return self._send_command_and_wait({'action': 'manage_cookies', 'cookie_action': action})

    def focus_element(self, element_id: int) -> Union[Dict[str, Any], ToolResult]:
        """
        Explicitly focus an element by scrolling it into view and clicking it.
        
        Use this BEFORE type_text when the target is a reply box, compose field,
        or contenteditable area that needs activation before accepting input.
        
        Args:
            element_id: The element ID from get_current_view()
        """
        return self._send_command_and_wait({
            'action': 'focus_element',
            'element_id': element_id
        })

    def click_by_text(self, text: str, element_type: str = "") -> Union[Dict[str, Any], ToolResult]:
        """
        Click an interactive element by its visible text content.
        
        This is more reliable than using element_id when dealing with dynamic UIs
        where IDs may change. Searches buttons, links, and interactive elements.
        
        Args:
            text: The visible text of the element to click (e.g., "Send", "Reply", "Submit")
            element_type: Optional CSS selector to narrow the search (e.g., "button" to only match buttons)
        
        Examples:
            - click_by_text("Reply") - click a Reply button
            - click_by_text("Send", "button") - click specifically a button labeled Send
            - click_by_text("Sign in") - click a sign-in link or button
        """
        payload = {'action': 'click_by_text', 'text': text}
        if element_type:
            payload['element_type'] = element_type
        return self._send_command_and_wait(payload)

    def click_coordinates(self, x: int, y: int) -> Union[Dict[str, Any], ToolResult]:
        """
        Click at specific pixel coordinates on the page.
        
        Use this as a LAST RESORT when element_id click and text-based click both fail.
        Coordinates are relative to the page viewport (visible area).
        
        Args:
            x: X coordinate (pixels from left edge of viewport)
            y: Y coordinate (pixels from top edge of viewport)
        """
        return self._send_command_and_wait({
            'action': 'click_coordinates',
            'x': x,
            'y': y
        })

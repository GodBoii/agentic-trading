# python-backend/browser_tools_server.py
"""
Server-side browser automation toolkit for mobile devices.
Uses Playwright to run headless browsers on the server, enabling
browser automation for platforms that cannot control local browsers.
"""

import logging
import json
import asyncio
import base64
import threading
import time
import os
from pathlib import Path
from typing import Dict, Any, Literal, Union, Optional, Tuple, List
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from agno.media import Image
from agno.tools import Toolkit
from agno.tools.function import ToolResult
from supabase_client import supabase_client

logger = logging.getLogger(__name__)

class ServerBrowserTools(Toolkit):
    """
    Server-side browser automation toolkit using Playwright.
    Manages browser contexts per session with automatic cleanup.
    """
    
    # Class-level browser instance (shared across all sessions)
    _browser: Optional[Browser] = None
    _playwright = None
    _browser_lock: Optional[asyncio.Lock] = None  # Lazily created on dedicated loop
    
    # Session contexts (one per user session)
    _contexts: Dict[str, BrowserContext] = {}
    _pages: Dict[str, Page] = {}
    
    # Dedicated event loop for Playwright async operations.
    # Eventlet monkey-patches asyncio, making loop.run_until_complete() fail
    # with "This event loop is already running". Running Playwright on a
    # separate OS thread with its own clean event loop avoids this entirely.
    _dedicated_loop: Optional[asyncio.AbstractEventLoop] = None
    _loop_thread: Optional[threading.Thread] = None
    _loop_init_lock = threading.Lock()
    _startup_error: Optional[str] = None
    
    def __init__(self, session_id: str, user_id: str, socketio=None, sid: str = None, redis_client=None, message_id: str = None, **kwargs):
        """
        Initialize server-side browser tools for a specific session.
        
        Args:
            session_id: Unique session identifier
            user_id: User identifier for storage paths
            socketio: Socket.IO instance for real-time updates (optional)
            sid: Socket.IO session ID (optional)
            redis_client: Redis client for pub/sub (optional)
            message_id: Current message ID for screenshot tracking (optional)
        """
        self.session_id = session_id
        self.user_id = user_id
        self.socketio = socketio
        self.sid = sid
        self.redis_client = redis_client
        self.message_id = message_id
        
        super().__init__(
            name="browser_tools",
            tools=[
                self.get_browser_status, self.navigate, self.get_current_view,
                self.click, self.type_text, self.scroll, self.go_back,
                self.go_forward, self.refresh_page, self.extract_text_from_element,
                self.extract_table_data, self.wait_for_element,
                self.list_tabs, self.open_new_tab, self.switch_to_tab, self.close_tab,
                self.close_browser, self.press_key,
                self.focus_element, self.click_by_text, self.click_coordinates,
            ],
        )
    
    @classmethod
    def _browser_binary_candidates(cls) -> List[Path]:
        """
        Return likely Chromium executable locations managed by Playwright.
        Supports custom PLAYWRIGHT_BROWSERS_PATH and default cache path.
        """
        base_paths: List[Path] = []
        env_path = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
        if env_path and env_path.strip() and env_path.strip() != "0":
            base_paths.append(Path(env_path.strip()))
        base_paths.append(Path.home() / ".cache" / "ms-playwright")

        seen = set()
        unique_base_paths: List[Path] = []
        for base in base_paths:
            key = str(base.resolve()) if base.exists() else str(base)
            if key not in seen:
                seen.add(key)
                unique_base_paths.append(base)

        candidate_patterns = [
            "chromium-*/chrome-linux/chrome",
            "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
            "chromium-*/chrome-win/chrome.exe",
            "chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe",
            "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
            "chromium_headless_shell-*/chrome-headless-shell-mac/chrome-headless-shell",
        ]

        candidates: List[Path] = []
        for base in unique_base_paths:
            if not base.exists():
                continue
            for pattern in candidate_patterns:
                candidates.extend(base.glob(pattern))
        return candidates

    @classmethod
    def _check_browser_installation(cls) -> Tuple[bool, str]:
        """Return whether Playwright Chromium binary appears installed."""
        candidates = cls._browser_binary_candidates()
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return True, str(candidate)
        if not candidates:
            return False, (
                "No Playwright Chromium binaries found in PLAYWRIGHT_BROWSERS_PATH "
                "or default ~/.cache/ms-playwright."
            )
        return False, "Playwright binary candidates exist but are not usable."

    @classmethod
    def _get_dedicated_loop(cls) -> asyncio.AbstractEventLoop:
        """Get or create a dedicated asyncio event loop running in a background thread.
        
        This is the key fix for eventlet compatibility:
        - Eventlet monkey-patches asyncio, making run_until_complete() fail
        - We create a SEPARATE OS thread with a clean asyncio event loop
        - All Playwright coroutines run on this dedicated loop
        - The calling eventlet green-thread blocks safely on future.result()
        """
        with cls._loop_init_lock:
            if cls._dedicated_loop is None or cls._dedicated_loop.is_closed():
                loop = asyncio.new_event_loop()
                cls._dedicated_loop = loop
                
                def _run_loop():
                    asyncio.set_event_loop(loop)
                    loop.run_forever()
                
                cls._loop_thread = threading.Thread(
                    target=_run_loop,
                    daemon=True,
                    name="playwright-event-loop"
                )
                cls._loop_thread.start()
                logger.info("[ServerBrowser] Started dedicated Playwright event loop thread")
        return cls._dedicated_loop
    
    @classmethod
    async def _ensure_browser(cls):
        """Ensure browser is launched (singleton pattern)."""
        # Lazily create asyncio.Lock on the dedicated loop thread
        if cls._browser_lock is None:
            cls._browser_lock = asyncio.Lock()
        
        async with cls._browser_lock:
            if cls._browser is None or not cls._browser.is_connected():
                installed, detail = cls._check_browser_installation()
                if not installed:
                    cls._startup_error = (
                        "Playwright Chromium is not installed on the server. "
                        "Run `playwright install --with-deps chromium` in the backend image. "
                        f"Details: {detail}"
                    )
                    logger.error(cls._startup_error)
                    raise RuntimeError(cls._startup_error)

                logger.info("Launching Playwright browser...")
                try:
                    cls._playwright = await async_playwright().start()
                    cls._browser = await cls._playwright.chromium.launch(
                        headless=True,
                        args=[
                            '--no-sandbox',
                            '--disable-setuid-sandbox',
                            '--disable-dev-shm-usage',
                            '--disable-gpu'
                        ]
                    )
                    cls._startup_error = None
                    logger.info("Browser launched successfully")
                except Exception as e:
                    cls._startup_error = str(e)
                    raise
    
    async def _get_or_create_context(self) -> BrowserContext:
        """Get or create browser context for this session."""
        await self._ensure_browser()
        
        if self.session_id not in self._contexts:
            logger.info(f"Creating new browser context for session {self.session_id}")
            self._contexts[self.session_id] = await self._browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
        
        return self._contexts[self.session_id]
    
    async def _get_or_create_page(self) -> Page:
        """Get or create page for this session."""
        if self.session_id not in self._pages:
            context = await self._get_or_create_context()
            self._pages[self.session_id] = await context.new_page()
            logger.info(f"Created new page for session {self.session_id}")
        
        return self._pages[self.session_id]
    
    async def _capture_screenshot(self) -> Optional[str]:
        """Capture screenshot and upload to Supabase (synchronous version for backward compatibility)."""
        try:
            page = await self._get_or_create_page()
            screenshot_bytes = await page.screenshot(full_page=False, type='png')
            
            # Upload to Supabase
            import uuid
            filename = f"{self.user_id}/{self.session_id}/{uuid.uuid4()}.png"
            
            supabase_client.storage.from_('media-uploads').upload(
                filename,
                screenshot_bytes,
                file_options={"content-type": "image/png"}
            )
            
            return filename
        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            return None
    
    def _emit_screenshot_event(self, action: str, page_url: str = None, screenshot_url: str = None):
        """Emit screenshot event to frontend via Redis pub/sub (non-blocking).
        
        The media-uploads bucket is private, so we generate a signed URL
        that the frontend can use directly in <img> tags without needing
        to construct URLs or have storage credentials.
        """
        if not self.redis_client or not screenshot_url:
            return
        
        try:
            # Generate a signed URL (valid for 2 hours) since the bucket is private
            # The raw storage path (e.g. user_id/session_id/uuid.png) won't work
            # with /object/public/ endpoint — it returns 400 Bad Request
            signed_url = screenshot_url  # fallback to raw path
            try:
                signed_response = supabase_client.storage.from_('media-uploads').create_signed_url(
                    path=screenshot_url,
                    expires_in=7200  # 2 hours
                )
                
                # Check for both camelCase (older SDKs) and snake_case (newer SDKs)
                if signed_response:
                    if 'signedURL' in signed_response:
                        signed_url = signed_response['signedURL']
                        logger.info(f"[Browser Screenshot] Generated signed URL (camelCase) for {action}")
                    elif 'signed_url' in signed_response:
                        signed_url = signed_response['signed_url']
                        logger.info(f"[Browser Screenshot] Generated signed URL (snake_case) for {action}")
                    else:
                        logger.warning(f"[Browser Screenshot] Signed URL response missing expected keys: {signed_response.keys()}")
            except Exception as sign_err:
                logger.error(f"[Browser Screenshot] Failed to generate signed URL: {sign_err}")
            
            event_data = {
                "screenshot_url": signed_url,
                "action": action,
                "page_url": page_url or "",
                "session_id": self.session_id,
                "message_id": self.message_id or "",
                "timestamp": int(time.time() * 1000)
            }
            
            # Publish to Redis channel
            channel = f"browser-screenshot:{self.session_id}"
            self.redis_client.publish(channel, json.dumps(event_data))
            logger.info(f"[Browser Screenshot] Published event to {channel}: {action}")
        except Exception as e:
            logger.error(f"[Browser Screenshot] Failed to emit event: {e}")
    
    async def _capture_and_emit_screenshot_async(self, action: str, page_url: str = None):
        """Capture screenshot and emit event asynchronously (fire-and-forget)."""
        try:
            screenshot_url = await self._capture_screenshot()
            if screenshot_url:
                self._emit_screenshot_event(action, page_url, screenshot_url)
        except Exception as e:
            logger.error(f"[Browser Screenshot] Async capture failed: {e}")
    
    def _run_async(self, coro):
        """Run an async coroutine on the dedicated Playwright event loop.
        
        Uses asyncio.run_coroutine_threadsafe() to submit the coroutine to the
        dedicated loop thread, then blocks the calling (eventlet green) thread
        until the result is available. This safely bridges eventlet's green threads
        with Playwright's native asyncio operations.
        """
        loop = self._get_dedicated_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=120)  # 2 min timeout for slow page loads
        except TimeoutError:
            future.cancel()
            logger.error("[ServerBrowser] Operation timed out after 120s")
            raise RuntimeError("Browser operation timed out")
        except Exception as e:
            logger.error(f"[ServerBrowser] Async operation failed: {e}")
            raise
    
    def _process_view_result(self, result: Dict[str, Any]) -> ToolResult:
        """Process result with screenshot."""
        if result.get("status") == "success" and "screenshot_path" in result:
            screenshot_path = result.pop("screenshot_path")
            try:
                image_bytes = supabase_client.storage.from_('media-uploads').download(screenshot_path)
                image_artifact = Image(content=image_bytes)
                return ToolResult(content=json.dumps(result), images=[image_artifact])
            except Exception as e:
                logger.error(f"Screenshot download failed: {e}")
                result["error"] = f"Could not retrieve screenshot"
                return ToolResult(content=json.dumps(result))
        
        return ToolResult(content=json.dumps(result))
    
    # ==================== PUBLIC TOOL METHODS ====================
    
    def get_browser_status(self) -> Dict[str, Any]:
        """
        Check if server-side browser is ready and launch if needed.
        
        This is the FIRST tool you must call before any other browser action.
        It will automatically launch a headless Chromium instance if needed.
        
        Returns:
            Dict with status='connected' if browser is ready, or status='disconnected' with error details.
        """
        try:
            is_ready = self.session_id in self._pages
            installed, install_detail = self._check_browser_installation()
            if not installed:
                return {
                    "status": "error",
                    "connected": False,
                    "ready": False,
                    "message": (
                        "Server-side browser dependencies are missing. "
                        "Playwright Chromium is not installed."
                    ),
                    "details": install_detail,
                }

            if self._startup_error:
                return {
                    "status": "error",
                    "connected": False,
                    "ready": False,
                    "message": "Server-side browser failed to start.",
                    "details": self._startup_error,
                }

            return {
                "status": "success",
                "connected": True,
                "ready": is_ready,
                "message": "Server-side browser is ready" if is_ready else "Browser will be initialized on first use"
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def navigate(self, url: str) -> Union[Dict[str, Any], ToolResult]:
        """Navigate to URL."""
        async def _navigate():
            try:
                if not url.startswith(('http://', 'https://')):
                    url_fixed = 'https://' + url
                else:
                    url_fixed = url
                
                page = await self._get_or_create_page()
                await page.goto(url_fixed, wait_until='networkidle', timeout=30000)
                
                # Fire screenshot capture in background (non-blocking)
                asyncio.create_task(self._capture_and_emit_screenshot_async('navigate', page.url))
                
                # Still capture screenshot for backward compatibility (agent can see it)
                screenshot_path = await self._capture_screenshot()
                
                return {
                    "status": "success",
                    "url": page.url,
                    "title": await page.title(),
                    "screenshot_path": screenshot_path
                }
            except PlaywrightTimeoutError:
                return {"status": "error", "error": "Page load timeout"}
            except Exception as e:
                logger.error(f"Navigation error: {e}")
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_navigate())
        return self._process_view_result(result)
    
    def get_current_view(self) -> Union[Dict[str, Any], ToolResult]:
        """Get current page view with screenshot and comprehensive interactive element detection."""
        async def _get_view():
            try:
                page = await self._get_or_create_page()
                
                # Fire screenshot capture in background
                asyncio.create_task(self._capture_and_emit_screenshot_async('get_current_view', page.url))
                
                screenshot_path = await self._capture_screenshot()
                
                # Comprehensive element detection (matches client-side browser-handler.js)
                interactive_elements = await page.evaluate('''() => {
                    const selectors = [
                        'a[href]', 'button', 'input', 'textarea', 'select',
                        '[role="button"]', '[role="link"]', '[role="textbox"]',
                        '[role="searchbox"]', '[role="combobox"]', '[role="menuitem"]',
                        '[role="tab"]', '[role="option"]', '[role="switch"]',
                        '[role="checkbox"]', '[role="radio"]',
                        '[contenteditable="true"]', '[contenteditable=""]',
                        '[tabindex]:not([tabindex="-1"])',
                        '[onclick]', '[data-action]', 'summary', 'label[for]'
                    ];

                    const elements = Array.from(document.querySelectorAll(selectors.join(', ')));
                    const visibleElements = [];
                    const seen = new WeakSet();
                    let nextId = Number(window.__aiosNextElementId || 1);

                    elements.forEach((el) => {
                        if (seen.has(el)) return;
                        seen.add(el);

                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        const isVisible = (
                            rect.width > 0 && rect.height > 0 &&
                            style.visibility !== 'hidden' && style.display !== 'none' &&
                            style.opacity !== '0' &&
                            rect.bottom >= 0 && rect.right >= 0 &&
                            rect.top <= window.innerHeight && rect.left <= window.innerWidth
                        );

                        if (isVisible) {
                            let elementId = el.getAttribute('data-aios-id');
                            if (!elementId) {
                                elementId = String(nextId++);
                                el.setAttribute('data-aios-id', elementId);
                            }

                            const tag = el.tagName.toLowerCase();
                            const type = el.getAttribute('type') || '';
                            const role = el.getAttribute('role') || '';
                            const isEditable = el.isContentEditable || tag === 'textarea' || 
                                (tag === 'input' && !['checkbox','radio','submit','button','file','hidden','image','reset'].includes(type));

                            visibleElements.push({
                                id: Number(elementId),
                                tag: tag,
                                type: type,
                                role: role,
                                text: (el.innerText || '').trim().substring(0, 100),
                                value: (el.value || '').substring(0, 100),
                                placeholder: el.getAttribute('placeholder') || '',
                                ariaLabel: el.getAttribute('aria-label') || '',
                                name: el.getAttribute('name') || '',
                                isEditable: isEditable,
                                isFocused: document.activeElement === el,
                                isContentEditable: el.isContentEditable,
                                bounds: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                            });
                        }
                    });
                    window.__aiosNextElementId = nextId;
                    return visibleElements;
                }''')
                
                return {
                    "status": "success",
                    "url": page.url,
                    "title": await page.title(),
                    "interactive_elements": interactive_elements,
                    "element_count": len(interactive_elements),
                    "editable_elements": len([e for e in interactive_elements if e.get('isEditable')]),
                    "focused_element": next((e for e in interactive_elements if e.get('isFocused')), None),
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                logger.error(f"Get view error: {e}")
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_get_view())
        return self._process_view_result(result)
    
    def click(self, element_id: int, description: str = "") -> Union[Dict[str, Any], ToolResult]:
        """Click element by its assigned ID from get_current_view()."""
        async def _click():
            try:
                page = await self._get_or_create_page()
                selector = f'[data-aios-id="{element_id}"]'
                
                # Scroll into view first
                await page.evaluate(f'''(sel) => {{
                    const el = document.querySelector(sel);
                    if (el) el.scrollIntoView({{ behavior: "smooth", block: "center" }});
                }}''', selector)
                await page.wait_for_timeout(300)
                
                # Try standard click
                try:
                    await page.click(selector, timeout=5000)
                except Exception:
                    # Fallback: force click via JS
                    await page.evaluate(f'''(sel) => {{
                        const el = document.querySelector(sel);
                        if (el) {{
                            el.focus();
                            el.click();
                            el.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true }}));
                        }}
                    }}''', selector)
                
                try:
                    await page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    pass
                
                # Fire screenshot capture in background
                asyncio.create_task(self._capture_and_emit_screenshot_async('click', page.url))
                
                screenshot_path = await self._capture_screenshot()
                
                return {
                    "status": "success",
                    "message": f"Clicked: {description or f'element #{element_id}'}",
                    "url": page.url,
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                logger.error(f"Click error: {e}")
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_click())
        return self._process_view_result(result)
    
    def type_text(self, element_id: int, text: str, description: str = "", clear_existing: bool = True) -> Union[Dict[str, Any], ToolResult]:
        """
        Type text into an element. Handles both standard inputs and contenteditable elements
        (like reply boxes in Slack, Gmail, Teams, etc.).
        
        Args:
            element_id: The element ID from get_current_view()
            text: Text to type
            description: Optional description of what we're typing into
            clear_existing: Whether to clear existing text first (default True)
        """
        async def _type():
            try:
                page = await self._get_or_create_page()
                selector = f'[data-aios-id="{element_id}"]'
                
                # Determine element type
                element_info = await page.evaluate(f'''(sel) => {{
                    const el = document.querySelector(sel);
                    if (!el) return null;
                    return {{
                        tag: el.tagName.toLowerCase(),
                        isContentEditable: el.isContentEditable,
                        type: el.getAttribute('type') || '',
                        role: el.getAttribute('role') || ''
                    }};
                }}''', selector)
                
                if not element_info:
                    return {"status": "error", "error": f"Element #{element_id} not found"}
                
                # Click to focus first (critical for reply boxes)
                try:
                    await page.click(selector, timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(200)
                
                if element_info.get('isContentEditable') or element_info.get('role') == 'textbox':
                    # ContentEditable strategy
                    if clear_existing:
                        await page.keyboard.press('Control+a')
                        await page.wait_for_timeout(50)
                        await page.keyboard.press('Backspace')
                        await page.wait_for_timeout(100)
                    
                    await page.keyboard.type(text, delay=30)
                else:
                    # Standard input/textarea
                    if clear_existing:
                        try:
                            await page.fill(selector, '', timeout=5000)
                        except Exception:
                            pass
                        await page.keyboard.press('Control+a')
                        await page.keyboard.press('Backspace')
                        await page.wait_for_timeout(50)
                    
                    await page.type(selector, text, delay=20)
                
                screenshot_path = await self._capture_screenshot()
                
                return {
                    "status": "success",
                    "message": f"Typed text into: {description or f'element #{element_id}'}",
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                logger.error(f"Type error: {e}")
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_type())
        return self._process_view_result(result)
    
    def scroll(self, direction: Literal['up', 'down']) -> Union[Dict[str, Any], ToolResult]:
        """Scroll page."""
        async def _scroll():
            try:
                page = await self._get_or_create_page()
                scroll_amount = 500 if direction == 'down' else -500
                await page.evaluate(f'window.scrollBy(0, {scroll_amount})')
                await page.wait_for_timeout(500)
                
                screenshot_path = await self._capture_screenshot()
                
                return {
                    "status": "success",
                    "message": f"Scrolled {direction}",
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_scroll())
        return self._process_view_result(result)
    
    def go_back(self) -> Union[Dict[str, Any], ToolResult]:
        """Navigate back."""
        async def _back():
            try:
                page = await self._get_or_create_page()
                await page.go_back(wait_until='networkidle')
                
                # Fire screenshot capture in background
                asyncio.create_task(self._capture_and_emit_screenshot_async('go_back', page.url))
                
                screenshot_path = await self._capture_screenshot()
                
                return {
                    "status": "success",
                    "url": page.url,
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_back())
        return self._process_view_result(result)
    
    def go_forward(self) -> Union[Dict[str, Any], ToolResult]:
        """Navigate forward."""
        async def _forward():
            try:
                page = await self._get_or_create_page()
                await page.go_forward(wait_until='networkidle')
                
                # Fire screenshot capture in background
                asyncio.create_task(self._capture_and_emit_screenshot_async('go_forward', page.url))
                
                screenshot_path = await self._capture_screenshot()
                
                return {
                    "status": "success",
                    "url": page.url,
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_forward())
        return self._process_view_result(result)
    
    def refresh_page(self) -> Union[Dict[str, Any], ToolResult]:
        """Refresh current page."""
        async def _refresh():
            try:
                page = await self._get_or_create_page()
                await page.reload(wait_until='networkidle')
                
                # Fire screenshot capture in background
                asyncio.create_task(self._capture_and_emit_screenshot_async('refresh', page.url))
                
                screenshot_path = await self._capture_screenshot()
                
                return {
                    "status": "success",
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_refresh())
        return self._process_view_result(result)

    def list_tabs(self) -> Union[Dict[str, Any], ToolResult]:
        """List all open tabs."""
        async def _list_tabs():
            try:
                context = await self._get_or_create_context()
                pages = context.pages
                tabs_info = []
                for i, p in enumerate(pages):
                    title = await p.title()
                    tabs_info.append({"index": i, "title": title, "url": p.url})
                
                return {
                    "status": "success",
                    "tabs": tabs_info,
                    "count": len(tabs_info)
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        return ToolResult(content=json.dumps(self._run_async(_list_tabs())))

    def open_new_tab(self, url: str) -> Union[Dict[str, Any], ToolResult]:
        """Open a new tab and navigate to URL."""
        async def _open_tab():
            try:
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                context = await self._get_or_create_context()
                page = await context.new_page()
                
                # Update current page reference for this session
                self._pages[self.session_id] = page
                
                await page.goto(url, wait_until='networkidle', timeout=30000)
                
                # Fire screenshot capture in background
                asyncio.create_task(self._capture_and_emit_screenshot_async('open_new_tab', page.url))
                
                screenshot_path = await self._capture_screenshot()
                
                return {
                    "status": "success",
                    "message": "Opened new tab",
                    "url": page.url,
                    "title": await page.title(),
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_open_tab())
        return self._process_view_result(result)

    def switch_to_tab(self, tab_index: int) -> Union[Dict[str, Any], ToolResult]:
        """Switch to a specific tab by index."""
        async def _switch_tab():
            try:
                context = await self._get_or_create_context()
                pages = context.pages
                
                if 0 <= tab_index < len(pages):
                    page = pages[tab_index]
                    self._pages[self.session_id] = page
                    await page.bring_to_front()
                    
                    # Fire screenshot capture in background
                    asyncio.create_task(self._capture_and_emit_screenshot_async('switch_to_tab', page.url))
                    
                    screenshot_path = await self._capture_screenshot()
                    
                    return {
                        "status": "success",
                        "message": f"Switched to tab {tab_index}",
                        "url": page.url,
                        "title": await page.title(),
                        "screenshot_path": screenshot_path
                    }
                else:
                    return {"status": "error", "error": f"Invalid tab index: {tab_index}"}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_switch_tab())
        return self._process_view_result(result)

    def close_tab(self, tab_index: int) -> Union[Dict[str, Any], ToolResult]:
        """Close a specific tab by index."""
        async def _close_tab():
            try:
                context = await self._get_or_create_context()
                pages = context.pages
                
                if 0 <= tab_index < len(pages):
                    page = pages[tab_index]
                    await page.close()
                    
                    # If we closed the current page, switch to the last one available
                    if len(context.pages) > 0:
                        self._pages[self.session_id] = context.pages[-1]
                    else:
                        # No pages left, clear the reference
                        if self.session_id in self._pages:
                            del self._pages[self.session_id]
                    
                    return {"status": "success", "message": f"Closed tab {tab_index}"}
                else:
                    return {"status": "error", "error": f"Invalid tab index: {tab_index}"}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        return ToolResult(content=json.dumps(self._run_async(_close_tab())))
    
    def extract_text_from_element(self, selector: str) -> Union[Dict[str, Any], ToolResult]:
        """Extract text from element."""
        async def _extract():
            try:
                page = await self._get_or_create_page()
                text = await page.text_content(selector, timeout=10000)
                
                return {
                    "status": "success",
                    "text": text
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        return ToolResult(content=json.dumps(self._run_async(_extract())))
    
    def extract_table_data(self, selector: str) -> Union[Dict[str, Any], ToolResult]:
        """Extract table data."""
        async def _extract_table():
            try:
                page = await self._get_or_create_page()
                table_data = await page.evaluate(f'''(selector) => {{
                    const table = document.querySelector(selector);
                    if (!table) return null;
                    
                    const rows = Array.from(table.querySelectorAll('tr'));
                    return rows.map(row => 
                        Array.from(row.querySelectorAll('td, th')).map(cell => cell.innerText)
                    );
                }}''', selector)
                
                return {
                    "status": "success",
                    "table_data": table_data
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        return ToolResult(content=json.dumps(self._run_async(_extract_table())))
    
    def wait_for_element(self, selector: str, timeout: int = 10) -> Union[Dict[str, Any], ToolResult]:
        """Wait for element to appear."""
        async def _wait():
            try:
                page = await self._get_or_create_page()
                await page.wait_for_selector(selector, timeout=timeout * 1000)
                
                return {
                    "status": "success",
                    "message": f"Element {selector} appeared"
                }
            except PlaywrightTimeoutError:
                return {"status": "error", "error": "Element did not appear in time"}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        return ToolResult(content=json.dumps(self._run_async(_wait())))
    
    def close_browser(self) -> Dict[str, Any]:
        """Close browser context for this session."""
        async def _close():
            try:
                if self.session_id in self._pages:
                    await self._pages[self.session_id].close()
                    del self._pages[self.session_id]
                
                if self.session_id in self._contexts:
                    await self._contexts[self.session_id].close()
                    del self._contexts[self.session_id]
                
                return {"status": "success", "message": "Browser closed"}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        return self._run_async(_close())

    def press_key(self, key: str) -> Union[Dict[str, Any], ToolResult]:
        """
        Press a keyboard key or combination in the browser.
        
        Args:
            key: Single key or combination with '+' separator.
                 Examples: "Enter", "Escape", "Tab", "Control+Enter", "Shift+Enter", "Control+a"
        """
        async def _press_key():
            try:
                page = await self._get_or_create_page()
                
                if '+' in key:
                    # Key combination
                    parts = key.split('+')
                    modifiers = parts[:-1]
                    final_key = parts[-1]
                    for mod in modifiers:
                        await page.keyboard.down(mod)
                    await page.keyboard.press(final_key)
                    for mod in reversed(modifiers):
                        await page.keyboard.up(mod)
                else:
                    await page.keyboard.press(key)
                
                await page.wait_for_timeout(500)
                screenshot_path = await self._capture_screenshot()
                
                return {
                    "status": "success",
                    "message": f"Pressed: {key}",
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_press_key())
        return self._process_view_result(result)

    def focus_element(self, element_id: int) -> Union[Dict[str, Any], ToolResult]:
        """
        Explicitly focus an element by scrolling it into view and clicking it.
        Use BEFORE type_text for reply boxes and contenteditable areas.
        
        Args:
            element_id: The element ID from get_current_view()
        """
        async def _focus():
            try:
                page = await self._get_or_create_page()
                selector = f'[data-aios-id="{element_id}"]'
                
                await page.evaluate(f'''(sel) => {{
                    const el = document.querySelector(sel);
                    if (el) el.scrollIntoView({{ behavior: "smooth", block: "center" }});
                }}''', selector)
                await page.wait_for_timeout(200)
                try:
                    await page.click(selector, timeout=5000)
                except Exception:
                    pass
                await page.wait_for_timeout(200)
                
                screenshot_path = await self._capture_screenshot()
                return {
                    "status": "success",
                    "message": f"Focused element #{element_id}",
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_focus())
        return self._process_view_result(result)

    def click_by_text(self, text: str, element_type: str = "") -> Union[Dict[str, Any], ToolResult]:
        """
        Click an interactive element by its visible text content.
        More reliable than element_id for dynamic UIs.
        
        Args:
            text: Visible text of the element (e.g., "Send", "Reply", "Submit")
            element_type: Optional CSS selector to narrow search (e.g., "button")
        """
        async def _click_text():
            try:
                page = await self._get_or_create_page()
                
                clicked = await page.evaluate('''({ searchText, elementType }) => {
                    const interactiveSelectors = elementType || 
                        'a, button, [role="button"], [role="link"], [role="menuitem"], [role="tab"], input[type="submit"], input[type="button"]';
                    const candidates = Array.from(document.querySelectorAll(interactiveSelectors));
                    
                    let target = candidates.find(el => {
                        const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
                        return t === searchText;
                    });
                    
                    if (!target) {
                        const lower = searchText.toLowerCase();
                        target = candidates.find(el => {
                            const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
                            return t.includes(lower);
                        });
                    }

                    if (!target) {
                        target = candidates.find(el => {
                            const label = (el.getAttribute('aria-label') || '').toLowerCase();
                            return label.includes(searchText.toLowerCase());
                        });
                    }
                    
                    if (target) {
                        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        target.click();
                        return { found: true, text: (target.innerText || '').substring(0, 80), tag: target.tagName };
                    }
                    return { found: false };
                }''', {"searchText": text, "elementType": element_type})
                
                if clicked.get('found'):
                    await page.wait_for_timeout(1000)
                    screenshot_path = await self._capture_screenshot()
                    return {
                        "status": "success",
                        "message": f"Clicked element with text: \"{clicked['text']}\" ({clicked['tag']})",
                        "screenshot_path": screenshot_path
                    }
                else:
                    return {"status": "error", "error": f"No clickable element found with text: \"{text}\""}
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_click_text())
        return self._process_view_result(result)

    def click_coordinates(self, x: int, y: int) -> Union[Dict[str, Any], ToolResult]:
        """
        Click at specific pixel coordinates on the page (last resort).
        
        Args:
            x: X coordinate (pixels from left)
            y: Y coordinate (pixels from top)
        """
        async def _click_coords():
            try:
                page = await self._get_or_create_page()
                await page.mouse.click(x, y)
                await page.wait_for_timeout(1000)
                screenshot_path = await self._capture_screenshot()
                return {
                    "status": "success",
                    "message": f"Clicked at ({x}, {y})",
                    "screenshot_path": screenshot_path
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        result = self._run_async(_click_coords())
        return self._process_view_result(result)
    
    @classmethod
    async def cleanup_all(cls):
        """Cleanup all browser resources (call on shutdown)."""
        try:
            for page in cls._pages.values():
                await page.close()
            for context in cls._contexts.values():
                await context.close()
            if cls._browser:
                await cls._browser.close()
            if cls._playwright:
                await cls._playwright.stop()
        except Exception as e:
            logger.error(f"[ServerBrowser] Error during cleanup: {e}")
        
        cls._pages.clear()
        cls._contexts.clear()
        cls._browser = None
        cls._playwright = None
        cls._browser_lock = None
        cls._startup_error = None
        
        # Stop the dedicated event loop
        if cls._dedicated_loop and not cls._dedicated_loop.is_closed():
            cls._dedicated_loop.call_soon_threadsafe(cls._dedicated_loop.stop)
            if cls._loop_thread:
                cls._loop_thread.join(timeout=5)
            cls._dedicated_loop.close()
            cls._dedicated_loop = None
            cls._loop_thread = None
            logger.info("[ServerBrowser] Dedicated event loop stopped")

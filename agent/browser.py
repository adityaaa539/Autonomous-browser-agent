import os
import base64
import logging
import asyncio
import functools
import json
from openai import AsyncOpenAI
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from playwright.async_api import (
    async_playwright,
    Playwright,
    Browser,
    BrowserContext,
    Page,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError
)

load_dotenv()

# Setup logging
logger = logging.getLogger("agent.browser")

class BrowserError(Exception):
    """Base exception for BrowserManager errors."""
    pass

class ElementNotFoundError(BrowserError):
    """Raised when an element cannot be found on the page."""
    pass

class NavigationTimeoutError(BrowserError):
    """Raised when page navigation times out."""
    pass

def retry_action(retries=3, delay=1):
    """Decorator to retry browser actions if they fail."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    logger.debug(f"Attempt {attempt + 1} failed for {func.__name__}: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(delay)
            logger.error(f"All {retries} attempts failed for {func.__name__}: {last_err}")
            if isinstance(last_err, BrowserError):
                raise last_err
            raise BrowserError(f"Action {func.__name__} failed: {last_err}") from last_err
        return wrapper
    return decorator

class BrowserManager:
    def __init__(self, headless: Optional[bool] = None):
        if headless is None:
            headless_str = os.getenv("HEADLESS", "true").lower()
            self.headless = headless_str == "true"
        else:
            self.headless = headless
        
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.openai_client = AsyncOpenAI()

    async def __aenter__(self):
        logger.debug("Starting Playwright and launching Chromium browser...")
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            logger.debug("Browser, context, and page initialized successfully.")
            return self
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            await self.close()
            raise BrowserError("Could not launch browser") from e

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.debug("Exiting browser context manager...")
        await self.close()

    async def close(self):
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            logger.debug("Browser successfully closed.")
        except Exception as e:
            logger.error(f"Error while closing browser: {e}")

    async def navigate(self, url: str) -> None:
        logger.debug(f"Navigating to {url}")
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        try:
            await self.page.goto(url, wait_until="networkidle")
        except PlaywrightTimeoutError as e:
            logger.error(f"Timeout navigating to {url}: {e}")
            raise NavigationTimeoutError(f"Timeout navigating to {url}") from e
        except Exception as e:
            logger.error(f"Error navigating to {url}: {e}")
            raise BrowserError(f"Failed to navigate to {url}") from e

    @retry_action(retries=3, delay=1)
    async def click(self, selector: str, timeout: int = 5000) -> None:
        logger.debug(f"Clicking element with selector: {selector}")
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        try:
            element = self.page.locator(selector)
            await element.wait_for(state="visible", timeout=timeout)
            await element.click()
            logger.debug(f"Successfully clicked element: {selector}")
        except PlaywrightTimeoutError as e:
            logger.error(f"Element not visible/clickable: {selector}")
            raise ElementNotFoundError(f"Element not found or not clickable: {selector}") from e
        except Exception as e:
            logger.error(f"Error clicking element {selector}: {e}")
            raise BrowserError(f"Error clicking element: {selector}") from e

    @retry_action(retries=3, delay=1)
    async def fill(self, selector: str, text: str, timeout: int = 5000) -> None:
        logger.debug(f"Filling element {selector} with text: {text}")
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        try:
            element = self.page.locator(selector)
            await element.wait_for(state="visible", timeout=timeout)
            await element.fill(text)
            logger.debug(f"Successfully filled element: {selector}")
        except PlaywrightTimeoutError as e:
            logger.error(f"Element not found to fill: {selector}")
            raise ElementNotFoundError(f"Element not found to fill: {selector}") from e
        except Exception as e:
            logger.error(f"Error filling element {selector}: {e}")
            raise BrowserError(f"Error filling element: {selector}") from e

    async def scroll(self, direction: str, pixels: int) -> None:
        logger.debug(f"Scrolling {direction} by {pixels} pixels")
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        try:
            if direction.lower() == "up":
                y = -pixels
            elif direction.lower() == "down":
                y = pixels
            else:
                raise ValueError("Direction must be 'up' or 'down'")
            await self.page.evaluate(f"window.scrollBy(0, {y})")
            logger.debug(f"Successfully scrolled {direction} by {pixels}")
        except Exception as e:
            logger.error(f"Error scrolling: {e}")
            raise BrowserError("Failed to scroll") from e

    async def get_page_text(self) -> str:
        logger.debug("Extracting page body text...")
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        try:
            text_content = await self.page.inner_text("body")
            return text_content
        except Exception as e:
            logger.error(f"Error extracting page text: {e}")
            raise BrowserError("Failed to extract page text") from e

    async def get_interactive_elements(self) -> List[Dict[str, Any]]:
        logger.debug("Identifying interactive elements...")
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        try:
            js_script = """
            () => {
                function getUniqueSelector(el) {
                    if (el.id) return `#${el.id}`;
                    let path = [];
                    while (el && el.nodeType === Node.ELEMENT_NODE) {
                        let selector = el.nodeName.toLowerCase();
                        if (el.id) {
                            selector += `#${el.id}`;
                            path.unshift(selector);
                            break;
                        } else {
                            let sib = el, nth = 1;
                            while (sib = sib.previousElementSibling) {
                                if (sib.nodeName.toLowerCase() === selector) nth++;
                            }
                            if (nth > 1) selector += `:nth-of-type(${nth})`;
                        }
                        path.unshift(selector);
                        el = el.parentNode;
                    }
                    return path.join(" > ");
                }

                const selector = 'button, a, input, textarea, select, [role="button"], [role="link"]';
                const elements = Array.from(document.querySelectorAll(selector));
                return elements.map((el) => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return null;
                    return {
                        tag: el.tagName.toLowerCase(),
                        text: el.innerText ? el.innerText.trim() : (el.value || ""),
                        type: el.type || null,
                        role: el.getAttribute("role") || null,
                        rect: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        selector: getUniqueSelector(el)
                    };
                }).filter(e => e !== null);
            }
            """
            elements = await self.page.evaluate(js_script)
            logger.debug(f"Found {len(elements)} interactive elements.")
            return elements
        except Exception as e:
            logger.error(f"Error getting interactive elements: {e}")
            raise BrowserError("Failed to list interactive elements") from e

    async def screenshot(self) -> str:
        logger.debug("Capturing base64 page screenshot...")
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        try:
            screenshot_bytes = await self.page.screenshot(type="png")
            base64_str = base64.b64encode(screenshot_bytes).decode("utf-8")
            return base64_str
        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}")
            raise BrowserError("Failed to capture screenshot") from e

    async def wait_for_selector(self, selector: str, timeout: int = 5000) -> bool:
        logger.debug(f"Waiting for selector: {selector} with timeout {timeout}ms")
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        try:
            await self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            logger.debug(f"Selector {selector} became visible.")
            return True
        except PlaywrightTimeoutError:
            logger.debug(f"Timed out waiting for selector {selector} after {timeout}ms.")
            return False
        except Exception as e:
            logger.error(f"Error waiting for selector {selector}: {e}")
            raise BrowserError(f"Error waiting for selector: {selector}") from e

    async def get_current_url(self) -> str:
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        return self.page.url

    async def analyze_page_with_vision(self, task: str) -> str:
        logger.debug(f"Analyzing page with vision for task: {task}")
        if not self.page:
            raise BrowserError("Browser not initialized. Use context manager.")
        try:
            screenshot_b64 = await self.screenshot()
            elements = await self.get_interactive_elements()
            page_text = await self.get_page_text()
            page_text_truncated = page_text[:2000]

            user_data = {
                "task": task,
                "page_text_summary": page_text_truncated,
                "interactive_elements": elements
            }
            user_text_json = json.dumps(user_data, indent=2)

            response = await self.openai_client.chat.completions.create(
                model="nex-agi/nex-n2-pro:free",
                max_tokens=1000,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a browser automation agent. Analyze the webpage screenshot and DOM to determine the next action needed to complete the task."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_text_json
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{screenshot_b64}"
                                }
                            }
                        ]
                    }
                ]
            )
            logger.debug("Successfully received response from GPT-4o.")
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in analyze_page_with_vision: {e}")
            raise BrowserError(f"Failed to analyze page with vision: {e}") from e

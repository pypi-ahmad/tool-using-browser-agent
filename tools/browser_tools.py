"""Async Playwright browser control: multi-tab session + LangChain tool wrappers.

Responsibility:
- Manage the Playwright Chromium browser lifecycle, tab creation, and isolation.
- Provide a robust multi-tier fallback locator chain (ARIA role -> text/label/placeholder -> raw CSS/XPath).
- Expose LangChain @tool wrappers for agent planning and execution.

What it must NOT do:
- Must not make LLM calls or manage LangGraph agent state.
- Must not be accessed across multiple threads or asyncio event loops simultaneously.

Next module to read:
- graph.py (see browser_actuator_node, where these tools are bound and called).
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from playwright.async_api import Locator, Page, async_playwright

from utils import bytes_to_b64, new_id


class BrowserSession:
    """Owns one Playwright browser and all its tabs. Lives in one background thread.

    Must not be driven from more than one asyncio event loop/thread at a time —
    Playwright's async objects are bound to the loop that created them.
    """

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._playwright = None
        self.browser = None
        self.pages: dict[str, Page] = {}
        self.active_tab: str | None = None

    async def start(self, start_url: str | None = None) -> str:
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=self.headless)
        return await self.open_new_tab(start_url)

    async def close(self) -> None:
        for page in list(self.pages.values()):
            await page.close()
        if self.browser is not None:
            await self.browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    def _page(self, tab_id: str | None) -> Page:
        tid = tab_id or self.active_tab
        if tid is None or tid not in self.pages:
            raise ValueError(f"Unknown tab_id: {tid!r}")
        return self.pages[tid]

    # ------------------------------------------------------------------
    # Tab management
    # ------------------------------------------------------------------

    async def open_new_tab(self, url: str | None = None) -> str:
        # browser.new_page() creates a fresh, isolated BrowserContext per call —
        # each tab gets its own cookies/storage, matching the spec's "maintain
        # separate context per tab" (not one shared context with multiple pages).
        page = await self.browser.new_page()
        tab_id = new_id("tab")
        self.pages[tab_id] = page
        self.active_tab = tab_id
        if url:
            await page.goto(url, wait_until="domcontentloaded")
        return tab_id

    async def switch_tab(self, tab_id: str) -> None:
        if tab_id not in self.pages:
            raise ValueError(f"Unknown tab_id: {tab_id!r}")
        self.active_tab = tab_id

    def list_tabs(self) -> dict[str, str]:
        return {tid: page.url for tid, page in self.pages.items()}

    async def close_tab(self, tab_id: str) -> None:
        page = self.pages.pop(tab_id, None)
        if page is not None:
            await page.close()
        if self.active_tab == tab_id:
            self.active_tab = next(iter(self.pages), None)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate(self, url: str, tab_id: str | None = None) -> str:
        page = self._page(tab_id)
        await page.goto(url, wait_until="domcontentloaded")
        return page.url

    async def go_back(self, tab_id: str | None = None) -> str:
        page = self._page(tab_id)
        await page.go_back(wait_until="domcontentloaded")
        return page.url

    async def go_forward(self, tab_id: str | None = None) -> str:
        page = self._page(tab_id)
        await page.go_forward(wait_until="domcontentloaded")
        return page.url

    async def scroll(
        self, direction: str = "down", amount: int = 800, tab_id: str | None = None
    ) -> None:
        # Units boundary: amount is in vertical viewport pixels.
        # Positive dy scrolls downwards; negative dy scrolls upwards.
        page = self._page(tab_id)
        dy = amount if direction == "down" else -amount
        await page.mouse.wheel(0, dy)

    async def wait_for_selector(
        self, selector: str, timeout: int = 5000, tab_id: str | None = None
    ) -> None:
        # Units boundary: timeout is in milliseconds (default 5000ms = 5 seconds).
        page = self._page(tab_id)
        await page.wait_for_selector(selector, timeout=timeout)

    # ------------------------------------------------------------------
    # Locator resolution (role -> text/label -> raw selector fallback chain)
    # ------------------------------------------------------------------

    @staticmethod
    async def _first_visible(locator: Locator) -> Locator | None:
        # Every fallback candidate below is filtered through this, so a hidden
        # duplicate element earlier in the DOM (e.g. a mobile-nav copy of a link)
        # never wins over a later, actually-visible match.
        if await locator.count() > 0 and await locator.first.is_visible():
            return locator.first
        return None

    async def _resolve_clickable(self, page: Page, target: str) -> Locator:
        for candidate in (
            page.get_by_role("link", name=target),
            page.get_by_role("button", name=target),
            page.get_by_text(target, exact=False),
        ):
            found = await self._first_visible(candidate)
            if found is not None:
                return found
        return page.locator(target).first

    async def _resolve_input(self, page: Page, target: str) -> Locator:
        for candidate in (
            page.get_by_label(target),
            page.get_by_placeholder(target),
            page.get_by_role("textbox", name=target),
            page.get_by_role("searchbox", name=target),
        ):
            found = await self._first_visible(candidate)
            if found is not None:
                return found
        return page.locator(target).first

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    async def click(self, selector_or_text: str, tab_id: str | None = None) -> None:
        page = self._page(tab_id)
        locator = await self._resolve_clickable(page, selector_or_text)
        await locator.click()

    async def fill(
        self, selector_or_text: str, value: str, tab_id: str | None = None
    ) -> None:
        page = self._page(tab_id)
        locator = await self._resolve_input(page, selector_or_text)
        await locator.fill(value)

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    async def extract_text(
        self, selector: str | None = None, tab_id: str | None = None
    ) -> str:
        page = self._page(tab_id)
        if selector:
            return await page.locator(selector).first.inner_text()
        return await page.inner_text("body")

    async def extract_table(
        self, selector: str, tab_id: str | None = None
    ) -> list[list[str]]:
        page = self._page(tab_id)
        rows = page.locator(selector).first.locator("tr")
        row_count = await rows.count()
        table: list[list[str]] = []
        for i in range(row_count):
            cells = rows.nth(i).locator("th, td")
            cell_count = await cells.count()
            table.append(
                [(await cells.nth(j).inner_text()).strip() for j in range(cell_count)]
            )
        return table

    async def extract_links(
        self, selector: str | None = None, tab_id: str | None = None
    ) -> list[dict[str, str]]:
        page = self._page(tab_id)
        scope = page.locator(selector) if selector else page.locator("a")
        count = await scope.count()
        links: list[dict[str, str]] = []
        for i in range(count):
            el = scope.nth(i)
            href = await el.get_attribute("href")
            if href:
                links.append({"text": (await el.inner_text()).strip(), "href": href})
        return links

    async def screenshot(
        self,
        full_page: bool = True,
        selector: str | None = None,
        tab_id: str | None = None,
    ) -> bytes:
        page = self._page(tab_id)
        if selector:
            return await page.locator(selector).first.screenshot()
        return await page.screenshot(full_page=full_page)


def build_tools(session: BrowserSession) -> list[Any]:
    """LangChain tool wrappers closed over one BrowserSession, for bind_tools().

    Every @tool docstring below is what the LLM sees as that tool's description —
    edit them for the model, not for a human reader. Names must stay in sync with
    graph.py's EXTRACTION_TOOLS set for extract_text/extract_table/extract_links/screenshot.
    """

    @tool
    async def navigate(url: str, tab_id: str | None = None) -> str:
        """Navigate a tab (default: active tab) to a URL. Returns the resulting URL."""
        return await session.navigate(url, tab_id)

    @tool
    async def click(selector_or_text: str, tab_id: str | None = None) -> str:
        """Click an element by visible text, ARIA role name, or CSS selector."""
        await session.click(selector_or_text, tab_id)
        return f"clicked {selector_or_text!r}"

    @tool
    async def fill(selector_or_text: str, value: str, tab_id: str | None = None) -> str:
        """Fill an input identified by its label, placeholder, role, or CSS selector."""
        await session.fill(selector_or_text, value, tab_id)
        return f"filled {selector_or_text!r}"

    @tool
    async def extract_text(
        selector: str | None = None, tab_id: str | None = None
    ) -> str:
        """Extract visible text from the page, or from one selector if given."""
        return await session.extract_text(selector, tab_id)

    @tool
    async def extract_table(
        selector: str, tab_id: str | None = None
    ) -> list[list[str]]:
        """Extract a <table> at the given selector as rows of cell text."""
        return await session.extract_table(selector, tab_id)

    @tool
    async def extract_links(
        selector: str | None = None, tab_id: str | None = None
    ) -> list[dict[str, str]]:
        """Extract {text, href} for links on the page, optionally scoped to a selector."""
        return await session.extract_links(selector, tab_id)

    @tool
    async def scroll(
        direction: str = "down", amount: int = 800, tab_id: str | None = None
    ) -> str:
        """Scroll the page 'up' or 'down' by amount pixels."""
        await session.scroll(direction, amount, tab_id)
        return f"scrolled {direction} {amount}px"

    @tool
    async def wait_for_selector(
        selector: str, timeout: int = 5000, tab_id: str | None = None
    ) -> str:
        """Wait until a selector appears in the DOM, up to timeout ms."""
        await session.wait_for_selector(selector, timeout, tab_id)
        return f"selector ready: {selector!r}"

    @tool
    async def go_back(tab_id: str | None = None) -> str:
        """Navigate a tab back one history entry."""
        return await session.go_back(tab_id)

    @tool
    async def go_forward(tab_id: str | None = None) -> str:
        """Navigate a tab forward one history entry."""
        return await session.go_forward(tab_id)

    @tool
    async def screenshot(
        full_page: bool = True, selector: str | None = None, tab_id: str | None = None
    ) -> str:
        """Take a screenshot (full page or one element) and return it as base64 PNG."""
        data = await session.screenshot(full_page, selector, tab_id)
        return bytes_to_b64(data)

    @tool
    async def open_new_tab(url: str | None = None) -> str:
        """Open a new browser tab, optionally navigating it, and make it active. Returns its tab_id."""
        return await session.open_new_tab(url)

    @tool
    async def switch_tab(tab_id: str) -> str:
        """Make the given tab_id the active tab for subsequent actions."""
        await session.switch_tab(tab_id)
        return f"active tab: {tab_id}"

    @tool
    async def list_tabs() -> dict[str, str]:
        """List all open tabs as {tab_id: current_url}."""
        return session.list_tabs()

    @tool
    async def close_tab(tab_id: str) -> str:
        """Close a tab by tab_id."""
        await session.close_tab(tab_id)
        return f"closed tab: {tab_id}"

    return [
        navigate,
        click,
        fill,
        extract_text,
        extract_table,
        extract_links,
        scroll,
        wait_for_selector,
        go_back,
        go_forward,
        screenshot,
        open_new_tab,
        switch_tab,
        list_tabs,
        close_tab,
    ]

"""Real headless-Playwright smoke test. No LLM, no network beyond data: URLs."""

import pytest

from tools.browser_tools import BrowserSession

PAGE_A = "data:text/html,<html><body><h1>Page A</h1><div id='go'>Click me</div></body></html>"
PAGE_B = "data:text/html,<html><body><h1>Page B</h1></body></html>"


@pytest.mark.asyncio
async def test_single_tab_navigate_and_extract():
    session = BrowserSession(headless=True)
    tab_id = await session.start(PAGE_A)
    try:
        text = await session.extract_text()
        assert "Page A" in text
        assert session.active_tab == tab_id
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_multi_tab_open_switch_close():
    session = BrowserSession(headless=True)
    first_tab = await session.start(PAGE_A)
    try:
        second_tab = await session.open_new_tab(PAGE_B)
        assert session.active_tab == second_tab
        assert set(session.list_tabs()) == {first_tab, second_tab}

        await session.switch_tab(first_tab)
        assert session.active_tab == first_tab
        text = await session.extract_text(tab_id=first_tab)
        assert "Page A" in text

        await session.close_tab(second_tab)
        assert second_tab not in session.list_tabs()
        assert session.active_tab == first_tab
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_click_resolves_by_text_fallback():
    session = BrowserSession(headless=True)
    await session.start(PAGE_A)
    try:
        # A plain <div> has no link/button role, so this exercises the get_by_text
        # fallback rung of the resolution chain, not the role-based ones.
        await session.click("Click me")
    finally:
        await session.close()

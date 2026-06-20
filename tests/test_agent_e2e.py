import pytest
from agent.runner import run_agent

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_extract_page_title():
    task = "Extract the main heading text of this web page."
    start_url = "https://example.com"
    res = await run_agent(task, start_url)
    
    assert res["success"] is True, f"Agent run failed: {res.get('error')}"
    assert res["result"] is not None
    assert len(str(res["result"]).strip()) > 0

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_form_fill(local_server):
    task = "Fill the input with ID name with 'E2E User', fill the input with ID email with 'e2e@test.com', select Developer role, click the Submit Form button, and then extract the final message in the result element."
    start_url = "http://localhost:8899/test_page.html"
    res = await run_agent(task, start_url)
    
    assert res["success"] is True, f"Agent run failed: {res.get('error')}"
    assert 3 <= res["step_count"] <= 15
    assert "E2E User" in str(res["result"])

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_navigate_and_extract():
    task = "Extract the title of the slideshow from this page."
    start_url = "https://httpbin.org/json"
    res = await run_agent(task, start_url)
    
    assert res["success"] is True, f"Agent run failed: {res.get('error')}"
    res_normalized = str(res["result"]).replace(" ", "").lower()
    assert "sampleslideshow" in res_normalized


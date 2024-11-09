# Testing tools

We have [tests](../engine/tests/). Not a ton but we should write more!

There is a [test_helpers.py](../engine/tests/test_helpers.py) file which includes
some utilities for writing tests.

```python
@pytest.fixture
def run_context():
```

This fixture returns a `RunContext` that many tools will expect to have
when they run.

To create your tool, add your own fixture like this:

```python
@pytest.fixture
def tool(run_context):
    tool = ZyteSearchTool()
    tool.run_context=run_context
    yield tool
```

This creates the `ZyteSearchTool` as a fixture. Then I can use it
in my tests like this:

```python
@pytest.mark.asyncio
async def test_screenshot(tool):
    res = await tool.get_page_screenshot("https://tatari.tv")
    print("Tatari screenshot: ", res)
```

Your tools are using `asyncio`, right? Then they need to use `@pytest.mark.asyncio`.

# Running tests

There are two helper commands in `agents.sh`

    ./agents.sh runtests tests/test_zyte.py
    ./agents.sh tests

The first runs a single test file, and the second runs all the tests in `engine`.

## Environment

There isn't any provision for a "test environment" yet, everything just uses your 
regular running env on your local machine. Keep that in mind.

# Using Async IO

It is good practice for our multi-tenant system to use asynchronous IO instead of
synchronous. If you use synchronous IO then everything in the python interpreter will
stop when you are waiting on I/O.

## Async web and API requests

The biggest place this is an issue is with web requests, because those can often by
very slow (also any API calls).

We still have lots of code using `requests`, but that library is synchronous. This code
should be replaced by using the `httpx` library which supports Async operation:

`httpx` is cool because its API mirrors the `requests` API closely.

Here is an example of how to do an async request:

```python
async with httpx.AsyncClient() as client:
    auth = httpx.BasicAuth(username=api_key, password="")
    params = {"url": url, "screenshot": True} if get_screenshot else {"url": url, "browserHtml": True}
    response = await client.post(
        "https://api.zyte.com/v1/extract",
        auth=auth,
        json=params,
        timeout=90,
    )
    response.raise_for_status()
    return response
```


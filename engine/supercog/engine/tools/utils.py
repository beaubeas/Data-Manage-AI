import markdown2
import json
from bleach.sanitizer import Cleaner
import httpx
import textwrap
import re

from supercog.engine.logging_handler import FileLogHandler

def markdown_to_html(markdown_content: str) -> str:
    # Convert Markdown to HTML
    html_content = markdown2.markdown(markdown_content)

    # Create a cleaner with only email-safe tags
    cleaner = Cleaner(tags=['a', 'p', 'br', 'strong', 'em', 'ul', 'ol', 'li','h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'img'])

    # Sanitize HTML
    return cleaner.clean(html_content)

# OpenAI logging via HTTPX client for OpenAI calls. Borrowed from Simon Willison

# Synchronous HTTP Client version

class _LogResponse(httpx.Response):
    def iter_bytes(self, *args, **kwargs):
        for chunk in super().iter_bytes(*args, **kwargs):
            print(chunk.decode(), end="")
            yield chunk


class _LogTransport(httpx.BaseTransport):
    def __init__(self, transport: httpx.BaseTransport):
        self.transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.transport.handle_request(request)
        return _LogResponse(
            status_code=response.status_code,
            headers=response.headers,
            stream=response.stream,
            extensions=response.extensions,
        )


def _no_accept_encoding(request: httpx.Request):
    request.headers.pop("accept-encoding", None)


def _log_response(response: httpx.Response):
    request = response.request
    print(f"Request: {request.method} {request.url}")
    print("  Headers:")
    for key, value in request.headers.items():
        if key.lower() == "authorization":
            value = "[...]"
        if key.lower() == "cookie":
            value = value.split("=")[0] + "=..."
        print(f"    {key}: {value}")
    print("  Body:")
    try:
        request_body = json.loads(request.content)
        print(
            textwrap.indent(json.dumps(request_body, indent=2), "    ")
        )
    except json.JSONDecodeError:
        print(textwrap.indent(request.content.decode(), "    "))
    print(f"Response: status_code={response.status_code}")
    print("  Headers:")
    for key, value in response.headers.items():
        if key.lower() == "set-cookie":
            value = value.split("=")[0] + "=..."
        print(f"    {key}: {value}")
    print("  Body:")

def logging_client() -> httpx.Client:
    return httpx.Client(
        transport=_LogTransport(httpx.HTTPTransport()),
        event_hooks={"request": [_no_accept_encoding], "response": [_log_response]},
    )

log_handler: FileLogHandler = None

async def _ano_accept_encoding(request: httpx.Request):
    request.headers.pop("accept-encoding", None)

# FIXME: We should probably move this logging into the FileHandler logging
# class which uses LangChain callbacks.
async def _alog_response(response: httpx.Response):
    global log_handler 
    request = response.request
    log_handler.printcount(f"Request: {request.method} {request.url}")
    if True:
        log_handler.printcount("  Headers:")
        for key, value in request.headers.items():
            if key.lower() == "authorization":
                value = "[...]"
            if key.lower() == "cookie":
                value = value.split("=")[0] + "=..."
            log_handler.printcount(f"    {key}: {value}")
    log_handler.printcount("  Body:")
    try:
        request_body = json.loads(request.content)
        log_handler.printcount(
            textwrap.indent(json.dumps(request_body, indent=2), "    ")
        )
    except json.JSONDecodeError:
        log_handler.printcount(textwrap.indent(request.content.decode(), "    "))
    log_handler.printcount(f"Response: status_code={response.status_code}")
    if True:
        log_handler.printcount("  Headers:")
        for key, value in response.headers.items():
            if key.lower() == "set-cookie":
                value = value.split("=")[0] + "=..."
            log_handler.printcount(f"    {key}: {value}")
    log_handler.printcount("  Body:")

async def async_logging_client(handler: FileLogHandler) -> httpx.AsyncClient:
    global log_handler
    log_handler = handler

    return httpx.AsyncClient(
        event_hooks={
            "request": [_ano_accept_encoding], 
            "response": [_alog_response]
        },
    )

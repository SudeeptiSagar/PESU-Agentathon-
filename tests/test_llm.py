"""CORE-02: llm() returns text or a validated tool call, retries once, uses the native API."""
import httpx
import pytest

from app import config, llm as llm_mod
from app.tools import TOOL_SCHEMAS


def _msg(content="", name=None, arguments=None):
    m = {"role": "assistant", "content": content}
    if name:
        m["tool_calls"] = [{"function": {"name": name, "arguments": arguments}}]
    return {"message": m, "prompt_eval_count": 10, "eval_count": 5}


class FakeChat:
    """Replaces llm._chat; replies with the queued responses in order."""

    def __init__(self, *responses):
        self.queue = list(responses)
        self.calls = []

    async def __call__(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        return self.queue.pop(0)


@pytest.fixture
def fake(monkeypatch):
    def install(*responses):
        chat = FakeChat(*responses)
        monkeypatch.setattr(llm_mod, "_chat", chat)
        return chat
    return install


MSGS = [{"role": "user", "content": "hi"}]


async def test_plain_text(fake):
    client = fake(_msg("Hello"))
    assert await llm_mod.llm(MSGS) == {"text": "Hello", "tool_call": None}
    assert client.calls[0]["tools"] is None


async def test_valid_tool_call_and_request_settings(fake):
    client = fake(_msg(name="fill_field", arguments={"field_id": "f2", "value_ref": "{dob}"}))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out["tool_call"] == {"name": "fill_field",
                                "args": {"field_id": "f2", "value_ref": "{dob}"}}
    assert client.calls[0]["tools"] is TOOL_SCHEMAS


async def test_malformed_then_valid_is_retried_once(fake):
    client = fake(_msg(name="click", arguments="{not json"),
                  _msg(name="click", arguments={"element_id": "b1"}))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out["tool_call"] == {"name": "click", "args": {"element_id": "b1"}}
    assert len(client.calls) == 2
    assert "not a valid tool call" in client.calls[1]["messages"][-1]["content"]
    assert client.calls[1]["messages"][:-1] == MSGS  # original history untouched


@pytest.mark.parametrize("name,args", [
    ("submit_form", {}),                                  # unknown tool
    ("click", {}),                                        # missing argument
    ("click", {"element_id": "b1", "extra": 1}),          # unexpected argument
    ("switch_tab", {"index": "two"}),                     # wrong type
    ("switch_tab", {"index": True}),                      # bool is not an integer
    ("scroll", {"direction": "sideways"}),                # not in enum
    ("click", [1, 2]),                                    # not an object
])
async def test_invalid_twice_gives_no_tool_call(fake, name, args):
    client = fake(_msg(name=name, arguments=args), _msg(name=name, arguments=args))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out == {"text": None, "tool_call": None}
    assert len(client.calls) == 2  # exactly one retry


async def test_tool_call_written_as_json_text(fake):
    fake(_msg('{"name": "scroll", "arguments": {"direction": "down"}}'))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out["tool_call"] == {"name": "scroll", "args": {"direction": "down"}}


async def test_prose_when_tools_offered_is_returned_as_text(fake):
    client = fake(_msg("I am not sure."))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out == {"text": "I am not sure.", "tool_call": None}
    assert len(client.calls) == 1


async def test_empty_reply_is_retried(fake):
    client = fake(_msg(""), _msg(name="go_back", arguments={}))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out["tool_call"] == {"name": "go_back", "args": {}}
    assert len(client.calls) == 2


async def test_string_arguments_are_tolerated(fake):
    fake(_msg(name="click", arguments='{"element_id": "b1"}'))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out["tool_call"] == {"name": "click", "args": {"element_id": "b1"}}


def test_base_url_strips_v1(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_URL", "http://host:11434/v1/")
    assert llm_mod._base_url() == "http://host:11434"


async def test_chat_request_shape(monkeypatch):
    """Real _chat against a mock HTTP transport: native endpoint, temperature 0, num_ctx, no think trace."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json=_msg("ok"))

    real = httpx.AsyncClient
    monkeypatch.setattr(llm_mod.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert seen["url"] == f"{llm_mod._base_url()}/api/chat"
    body = seen["body"]
    assert body["model"] == config.LLM_MODEL and body["stream"] is False and body["think"] is False
    assert body["options"] == {"temperature": 0, "num_ctx": config.NUM_CTX}
    assert body["tools"] == TOOL_SCHEMAS


async def test_think_unsupported_retries_without_flag(monkeypatch):
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        bodies.append(body)
        if "think" in body:
            return httpx.Response(400, json={"error": "model does not support think"})
        return httpx.Response(200, json=_msg("ok"))

    real = httpx.AsyncClient
    monkeypatch.setattr(llm_mod.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    assert (await llm_mod.llm(MSGS))["text"] == "ok"
    assert len(bodies) == 2 and "think" not in bodies[1]

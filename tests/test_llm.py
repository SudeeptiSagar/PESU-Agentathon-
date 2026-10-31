"""CORE-02: llm() returns text or a validated tool call, retries once, uses temperature 0."""
from types import SimpleNamespace as NS

import pytest

from app import config, llm as llm_mod
from app.tools import TOOL_SCHEMAS


def _msg(content=None, name=None, arguments=None):
    calls = [NS(function=NS(name=name, arguments=arguments))] if name else None
    return NS(content=content, tool_calls=calls)


class FakeClient:
    """Stands in for AsyncOpenAI; replies with the queued messages in order."""

    def __init__(self, *messages):
        self.queue = list(messages)
        self.calls = []
        self.chat = NS(completions=NS(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return NS(choices=[NS(message=self.queue.pop(0))],
                  usage=NS(prompt_tokens=10, completion_tokens=5))


@pytest.fixture
def fake(monkeypatch):
    def install(*messages):
        client = FakeClient(*messages)
        monkeypatch.setattr(llm_mod, "_get_client", lambda: client)
        return client
    return install


MSGS = [{"role": "user", "content": "hi"}]


async def test_plain_text(fake):
    client = fake(_msg(content="Hello"))
    assert await llm_mod.llm(MSGS) == {"text": "Hello", "tool_call": None}
    assert "tools" not in client.calls[0]


async def test_valid_tool_call_and_request_settings(fake):
    client = fake(_msg(name="fill_field", arguments='{"field_id": "f2", "value_ref": "{dob}"}'))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out["tool_call"] == {"name": "fill_field",
                                "args": {"field_id": "f2", "value_ref": "{dob}"}}
    call = client.calls[0]
    assert call["temperature"] == 0
    assert call["model"] == config.LLM_MODEL
    assert call["extra_body"] == {"options": {"num_ctx": config.NUM_CTX}}
    assert call["tools"] is TOOL_SCHEMAS


async def test_malformed_then_valid_is_retried_once(fake):
    client = fake(_msg(name="click", arguments="{not json"),
                  _msg(name="click", arguments='{"element_id": "b1"}'))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out["tool_call"] == {"name": "click", "args": {"element_id": "b1"}}
    assert len(client.calls) == 2
    assert "not a valid tool call" in client.calls[1]["messages"][-1]["content"]
    assert client.calls[1]["messages"][:-1] == MSGS  # original history untouched


@pytest.mark.parametrize("name,args", [
    ("submit_form", "{}"),                                  # unknown tool
    ("click", "{}"),                                        # missing argument
    ("click", '{"element_id": "b1", "extra": 1}'),          # unexpected argument
    ("switch_tab", '{"index": "two"}'),                     # wrong type
    ("switch_tab", '{"index": true}'),                      # bool is not an integer
    ("scroll", '{"direction": "sideways"}'),                # not in enum
    ("click", "[1, 2]"),                                    # not an object
])
async def test_invalid_twice_gives_no_tool_call(fake, name, args):
    client = fake(_msg(name=name, arguments=args), _msg(name=name, arguments=args))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out == {"text": None, "tool_call": None}
    assert len(client.calls) == 2  # exactly one retry


async def test_tool_call_written_as_json_text(fake):
    fake(_msg(content='{"name": "scroll", "arguments": {"direction": "down"}}'))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out["tool_call"] == {"name": "scroll", "args": {"direction": "down"}}


async def test_prose_when_tools_offered_is_returned_as_text(fake):
    client = fake(_msg(content="I am not sure."))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out == {"text": "I am not sure.", "tool_call": None}
    assert len(client.calls) == 1


async def test_empty_reply_is_retried(fake):
    client = fake(_msg(content=""), _msg(name="go_back", arguments="{}"))
    out = await llm_mod.llm(MSGS, TOOL_SCHEMAS)
    assert out["tool_call"] == {"name": "go_back", "args": {}}
    assert len(client.calls) == 2

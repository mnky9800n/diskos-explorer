"""LLM client tests: wiring only, no network (client is dependency-injected)."""

from types import SimpleNamespace

from diskos.config import Config, LLMProfile
from diskos.llm.client import LLMClient
from diskos.llm.profiles import system_prompt_for


class FakeCompletions:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


def _config():
    profile = LLMProfile(name="jack-serve", base_url="http://x/v1", model="m", api_key_env="NONE")
    return Config(
        diskos_root="", local_sample="", prefer="local_sample",
        default_profile="jack-serve", profiles={"jack-serve": profile},
    )


def test_from_profile_reads_transport():
    client = LLMClient.from_profile("jack-serve", _config())
    assert client.base_url == "http://x/v1"
    assert client.model == "m"
    assert client.system == system_prompt_for("jack-serve")


def test_chat_uses_injected_client_and_model():
    fake = FakeClient()
    client = LLMClient(base_url="http://x/v1", model="m", system="SYS", client=fake)
    out = client.ask("hello")
    assert out == "ok"
    kwargs = fake.chat.completions.last_kwargs
    assert kwargs["model"] == "m"
    # System prompt is prepended.
    assert kwargs["messages"][0] == {"role": "system", "content": "SYS"}
    assert kwargs["messages"][1]["content"] == "hello"


def test_no_em_dash_rule_in_system_prompts():
    assert "—" not in system_prompt_for("wiki-author")
    assert "em dash" in system_prompt_for("wiki-author").lower()

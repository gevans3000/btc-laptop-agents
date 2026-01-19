import os
from laptop_agents.core.logger import scrub_secrets


def test_scrub_env_secrets():
    os.environ["TEST_API_KEY"] = "supersecretkey12345678"
    result = scrub_secrets("My key is supersecretkey12345678")
    assert "supersecretkey12345678" not in result
    assert "***" in result
    del os.environ["TEST_API_KEY"]


def test_scrub_patterns():
    text = 'api_key="abc123456789012345"'
    result = scrub_secrets(text)
    assert "abc123456789012345" not in result

from agentboard.security.sensitivity import SECURITY_KEYWORDS, check_security_sensitive


def test_security_keywords_has_seven_categories():
    expected = {"auth", "crypto", "subprocess", "sql", "network", "deserialization", "filesystem"}
    assert set(SECURITY_KEYWORDS.keys()) == expected


def test_empty_diff_returns_not_sensitive():
    result = check_security_sensitive("")
    assert result == {"sensitive": False, "categories": [], "matches": []}


def test_password_line_triggers_auth_category():
    diff = "+password = 'secret'\n"
    result = check_security_sensitive(diff)
    assert result["sensitive"] is True
    assert "auth" in result["categories"]


def test_case_insensitive_matching():
    result = check_security_sensitive("+PASSWORD = 'x'\n")
    assert result["sensitive"] is True


def test_context_lines_ignored():
    diff = " password = 'x'\n context line with subprocess\n"
    result = check_security_sensitive(diff)
    assert result["sensitive"] is False


def test_multiple_categories_aggregated():
    diff = "+password = 'x'\n+subprocess.run(['ls'])\n"
    result = check_security_sensitive(diff)
    assert result["categories"] == ["auth", "subprocess"]


def test_mcp_tool_registered():
    import asyncio

    from agentboard.mcp_server import list_tools

    tools = asyncio.run(list_tools())
    names = [t.name for t in tools]
    assert "agentboard_check_security_sensitive" in names


def test_mcp_dispatch_returns_result():
    import asyncio

    from agentboard.mcp_server import call_tool

    result = asyncio.run(
        call_tool(
            "agentboard_check_security_sensitive",
            {"diff": "+password = 'x'\n"},
        )
    )
    import json

    payload = json.loads(result[0].text)
    assert payload["sensitive"] is True
    assert "auth" in payload["categories"]

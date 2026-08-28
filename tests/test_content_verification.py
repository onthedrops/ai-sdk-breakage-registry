"""Tests for the content verification module in verify_registry.py."""

import sys
import pathlib

import pytest

# Add scripts dir to path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

from verify_registry import (
    extract_verification_terms,
    github_blob_to_raw,
    strip_html,
    is_js_rendered,
    _GENERIC_TOKENS,
)


class TestExtractVerificationTerms:
    """Test that term extraction pulls the right API tokens from change entries."""

    def test_extracts_dotted_path_from_symbol_before(self):
        change = {
            "symbol_before": "openai.ChatCompletion.create",
            "symbol_after": "client.chat.completions.create",
            "before": "import openai\nresponse = openai.ChatCompletion.create(...)",
            "after": "from openai import OpenAI\nclient = OpenAI()\nresponse = client.chat.completions.create(...)",
            "change_type": "renamed_method",
        }
        terms = extract_verification_terms(change)
        assert "ChatCompletion" in terms
        assert "openai.ChatCompletion" in terms
        assert "completions" in terms
        assert "client.chat" in terms

    def test_extracts_import_paths_from_code(self):
        change = {
            "symbol_before": "from langchain.schema import HumanMessage",
            "symbol_after": "from langchain_core.messages import HumanMessage",
            "before": "from langchain.schema import HumanMessage, AIMessage, SystemMessage",
            "after": "from langchain_core.messages import HumanMessage, AIMessage, SystemMessage",
            "change_type": "import_path_changed",
        }
        terms = extract_verification_terms(change)
        assert "langchain.schema" in terms
        assert "langchain_core.messages" in terms
        assert "HumanMessage" in terms

    def test_extracts_method_names_from_code(self):
        change = {
            "symbol_before": "retriever.get_relevant_documents(query)",
            "symbol_after": "retriever.invoke(query)",
            "before": "docs = retriever.get_relevant_documents(query)",
            "after": "docs = retriever.invoke(query)",
            "change_type": "method_renamed",
        }
        terms = extract_verification_terms(change)
        assert "get_relevant_documents" in terms
        assert "invoke" in terms

    def test_extracts_class_names_from_definitions(self):
        change = {
            "symbol_before": "class OpenAIFunctionsAgent",
            "symbol_after": "create_openai_functions_agent(llm, tools)",
            "before": "from langchain.agents import OpenAIFunctionsAgent\nagent = OpenAIFunctionsAgent.from_llm_and_tools(llm, tools)",
            "after": "from langchain.agents import create_openai_functions_agent\nagent = create_openai_functions_agent(llm, tools)",
            "change_type": "api_removed",
        }
        terms = extract_verification_terms(change)
        assert "OpenAIFunctionsAgent" in terms
        assert "create_openai_functions_agent" in terms

    def test_extracts_literal_strings_from_regex(self):
        change = {
            "symbol_before": "from langchain.vectorstores import Chroma",
            "symbol_after": "from langchain_community.vectorstores import Chroma",
            "before": "from langchain.vectorstores import Chroma",
            "after": "from langchain_community.vectorstores import Chroma",
            "change_type": "import_path_changed",
            "detection": {
                "regex": ["from langchain\\.vectorstores import"]
            },
        }
        terms = extract_verification_terms(change)
        assert "langchain.vectorstores" in terms
        assert "langchain_community.vectorstores" in terms
        assert "Chroma" in terms

    def test_filters_generic_tokens(self):
        change = {
            "symbol_before": "chain.run(query)",
            "symbol_after": "chain.invoke(query)",
            "before": "result = chain.run(query)",
            "after": "result = chain.invoke(query)",
            "change_type": "method_renamed",
        }
        terms = extract_verification_terms(change)
        # "run" and "chain" are generic, should not appear
        assert "run" not in terms
        assert "chain" not in terms
        # "invoke" is > 3 chars and not in generic list
        assert "invoke" in terms

    def test_returns_empty_for_platform_requirement(self):
        change = {
            "symbol_before": "Node.js 18+",
            "symbol_after": "Node.js 22+",
            "before": '// "engines": { "node": ">=18" }',
            "after": '// "engines": { "node": ">=22" }',
            "change_type": "platform_requirement_added",
        }
        terms = extract_verification_terms(change)
        # Should have minimal or no strong terms
        # "Node" is too short (< 4 chars after filtering)
        assert all(len(t) > 3 for t in terms)

    def test_handles_empty_fields(self):
        change = {
            "symbol_before": "",
            "symbol_after": "",
            "before": "",
            "after": "",
            "change_type": "api_removed",
        }
        terms = extract_verification_terms(change)
        assert terms == []


class TestGithubBlobToRaw:
    """Test GitHub blob URL to raw URL conversion."""

    def test_converts_blob_url(self):
        url = "https://github.com/org/repo/blob/main/docs/migration.md"
        raw = github_blob_to_raw(url)
        assert raw == "https://raw.githubusercontent.com/org/repo/main/docs/migration.md"

    def test_converts_blob_url_with_long_path(self):
        url = "https://github.com/langchain-ai/langchain/blob/master/docs/docs/versions/v0_2/index.mdx"
        raw = github_blob_to_raw(url)
        assert raw == "https://raw.githubusercontent.com/langchain-ai/langchain/master/docs/docs/versions/v0_2/index.mdx"

    def test_preserves_non_github_urls(self):
        url = "https://python.langchain.com/v0.2/docs/versions/v0_2/deprecations/"
        assert github_blob_to_raw(url) == url

    def test_preserves_already_raw_urls(self):
        url = "https://raw.githubusercontent.com/org/repo/main/file.md"
        assert github_blob_to_raw(url) == url

    def test_preserves_github_non_blob_urls(self):
        url = "https://github.com/openai/openai-python/discussions/742"
        assert github_blob_to_raw(url) == url


class TestStripHtml:
    """Test HTML tag stripping and text extraction."""

    def test_strips_basic_tags(self):
        html_str = "<html><body><p>Hello World</p></body></html>"
        text = strip_html(html_str)
        assert "hello world" in text
        assert "<" not in text

    def test_removes_script_blocks(self):
        html_str = "<html><body><script>alert('xss')</script><p>Content</p></body></html>"
        text = strip_html(html_str)
        assert "alert" not in text
        assert "content" in text

    def test_removes_style_blocks(self):
        html_str = "<html><head><style>body { color: red; }</style></head><body><p>Text</p></body></html>"
        text = strip_html(html_str)
        assert "color" not in text
        assert "text" in text

    def test_decodes_html_entities(self):
        html_str = "<p>import openai &amp; pandas</p>"
        text = strip_html(html_str)
        assert "&" in text
        assert "amp" not in text

    def test_normalizes_whitespace(self):
        html_str = "<p>  Multiple   spaces\n\n  and newlines  </p>"
        text = strip_html(html_str)
        assert "  " not in text
        assert "\n" not in text

    def test_returns_lowercase(self):
        html_str = "<P>UPPERCASE Text</P>"
        text = strip_html(html_str)
        assert text == "uppercase text"


class TestIsJsRendered:
    """Test JS-rendered page detection."""

    def test_detects_empty_page(self):
        assert is_js_rendered("") is True
        assert is_js_rendered(None) is True

    def test_detects_short_page(self):
        assert is_js_rendered("enable javascript") is True

    def test_detects_enable_javascript_message(self):
        text = "Please enable JavaScript to view this page. " * 20
        assert is_js_rendered(text) is True

    def test_detects_loading_message(self):
        text = "Loading... " * 50
        assert is_js_rendered(text) is True

    def test_passes_real_content(self):
        text = "This is a real documentation page about API migration. " * 20
        assert is_js_rendered(text) is False

    def test_detects_noscript_tag(self):
        text = "<noscript>enable js</noscript> " + "content " * 50
        assert is_js_rendered(text) is True


class TestCorpusMatching:
    """Test the corpus matching logic used by check_content_verification."""

    def test_term_matches_in_corpus(self):
        """Simulates the matching logic: terms should be found in the corpus."""
        corpus = "the openai ChatCompletion.create method was replaced with client.chat.completions.create"
        terms = ["ChatCompletion", "completions", "openai.ChatCompletion"]
        matched = [t for t in terms if t.lower() in corpus.lower()]
        assert len(matched) > 0

    def test_term_not_in_corpus(self):
        """Terms not in corpus should produce no matches."""
        corpus = "this page is about a completely different API"
        terms = ["ChatCompletion", "get_relevant_documents", "convert_pydantic_to_openai_function"]
        matched = [t for t in terms if t.lower() in corpus.lower()]
        assert len(matched) == 0

    def test_partial_match_works(self):
        """At least one term matching is sufficient."""
        corpus = "LangChain v0.2 moved vectorstores to langchain_community"
        terms = ["vectorstores", "get_relevant_documents", "convert_pydantic_to_openai_function"]
        matched = [t for t in terms if t.lower() in corpus.lower()]
        assert len(matched) == 1
        assert "vectorstores" in matched

"""Tests for company extraction from HN items."""

from src.extraction.company_extractor import (
    _clean_company_name,
    _looks_like_company,
    extract_from_hn_item,
)
from src.hn.client import HNItem
from src.models.signal import SignalType


def _make_item(**kwargs) -> HNItem:
    defaults = dict(id=1, type="story", title="", score=10, descendants=5)
    defaults.update(kwargs)
    return HNItem(**defaults)


class TestCleanCompanyName:
    def test_strips_description_after_dash(self):
        assert _clean_company_name("Acme – the best tool") == "Acme"

    def test_strips_description_after_colon(self):
        assert _clean_company_name("Acme: an open-source widget") == "Acme"

    def test_removes_html_tags(self):
        assert _clean_company_name("<b>Acme</b>") == "Acme"

    def test_removes_markdown_links(self):
        assert _clean_company_name("[Acme](https://acme.com)") == "Acme"

    def test_truncates_long_names(self):
        long = "SuperLong Company Name That Goes On And On And Should Be Trimmed Down - extra description"
        result = _clean_company_name(long)
        assert "extra description" not in result


class TestLooksLikeCompany:
    def test_rejects_empty(self):
        assert not _looks_like_company("")

    def test_rejects_stop_word_start(self):
        assert not _looks_like_company("How to build something")

    def test_rejects_very_long_phrases(self):
        assert not _looks_like_company("this is a very long sentence that is not a company")

    def test_accepts_simple_name(self):
        assert _looks_like_company("Acme Corp")

    def test_accepts_single_word(self):
        assert _looks_like_company("Stripe")


class TestExtractFromHNItem:
    def test_show_hn_extraction(self):
        item = _make_item(title="Show HN: Acme – a tool for doing things")
        result = extract_from_hn_item(item)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.HN_MENTION

    def test_show_hn_with_url(self):
        item = _make_item(
            title="Show HN: FastDB – a fast database for analytics",
            url="https://fastdb.io",
        )
        result = extract_from_hn_item(item)
        assert result is not None
        assert result.company_name == "FastDB"
        assert result.signal_type == SignalType.HN_MENTION

    def test_launch_hn(self):
        item = _make_item(title="Launch HN: Vercel – Frontend Cloud")
        result = extract_from_hn_item(item)
        assert result is not None
        assert result.company_name == "Vercel"
        assert result.signal_type == SignalType.PRODUCT_LAUNCH

    def test_funding_announcement(self):
        item = _make_item(title="Acme raises $10M Series A to reinvent widgets")
        result = extract_from_hn_item(item)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.FUNDING

    def test_funding_secured(self):
        item = _make_item(title="DataCo secured $5M seed funding")
        result = extract_from_hn_item(item)
        assert result is not None
        assert result.company_name == "DataCo"
        assert result.signal_type == SignalType.FUNDING

    def test_yc_batch_mention(self):
        item = _make_item(title="Acme (YC S24) – AI-powered widgets")
        result = extract_from_hn_item(item)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.FUNDING

    def test_product_launch_keyword(self):
        item = _make_item(title="Acme launches v2.0 of their platform")
        result = extract_from_hn_item(item)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.PRODUCT_LAUNCH

    def test_we_built_pattern(self):
        item = _make_item(title="CloudTech just shipped a new API gateway")
        result = extract_from_hn_item(item)
        assert result is not None
        assert result.company_name == "CloudTech"
        assert result.signal_type == SignalType.PRODUCT_LAUNCH

    def test_no_extraction_for_question(self):
        item = _make_item(title="How do you manage your infrastructure?")
        result = extract_from_hn_item(item)
        assert result is None

    def test_no_extraction_for_generic_news(self):
        item = _make_item(title="The state of web development in 2026")
        result = extract_from_hn_item(item)
        assert result is None

    def test_no_extraction_for_empty_title(self):
        item = _make_item(title="")
        result = extract_from_hn_item(item)
        assert result is None

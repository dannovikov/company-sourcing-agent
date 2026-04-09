"""Tests for Google News article parser / company extractor."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.google.client import NewsArticle
from src.google.parser import (
    GoogleExtractionResult,
    extract_from_article,
    _clean_company_name,
    _looks_like_company,
)
from src.models.signal import SignalType


def _make_article(title: str, **kwargs) -> NewsArticle:
    defaults = dict(
        url="https://example.com/article",
        source="TechCrunch",
        published_at=datetime(2025, 4, 9, tzinfo=timezone.utc),
        query="test query",
    )
    defaults.update(kwargs)
    return NewsArticle(title=title, **defaults)


class TestExtractFromArticle:
    def test_funding_raises(self):
        article = _make_article("Acme raises $10M Series A to revolutionize payments")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.FUNDING

    def test_funding_secures(self):
        article = _make_article("BetaCo secures $5M seed funding")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "BetaCo"
        assert result.signal_type == SignalType.FUNDING

    def test_funding_closes(self):
        article = _make_article("DeepTech closes $50M Series B round")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "DeepTech"
        assert result.signal_type == SignalType.FUNDING

    def test_product_launch(self):
        article = _make_article("Acme launches new AI-powered analytics platform")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.PRODUCT_LAUNCH

    def test_product_unveils(self):
        article = _make_article("StartupX unveils breakthrough quantum computing chip")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "StartupX"
        assert result.signal_type == SignalType.PRODUCT_LAUNCH

    def test_introducing(self):
        article = _make_article("Introducing Acme: the future of cloud storage")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.PRODUCT_LAUNCH

    def test_stealth_reveal(self):
        article = _make_article("Acme emerges from stealth with $20M in funding")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.PRODUCT_LAUNCH

    def test_partnership(self):
        article = _make_article("Acme partners with Google to expand AI capabilities")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.PARTNERSHIP

    def test_hiring(self):
        article = _make_article("Acme is hiring 50 engineers for new AI lab")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "Acme"
        assert result.signal_type == SignalType.HIRING_SURGE

    def test_no_match_returns_none(self):
        article = _make_article("How to build a startup in 2025")
        result = extract_from_article(article)
        assert result is None

    def test_empty_title_returns_none(self):
        article = _make_article("")
        result = extract_from_article(article)
        assert result is None

    def test_strips_publisher_suffix(self):
        article = _make_article(
            "Acme raises $10M seed round - TechCrunch"
        )
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "Acme"

    def test_stop_word_title_returns_none(self):
        article = _make_article("Why launches fail in the startup world")
        result = extract_from_article(article)
        # "Why" is a stop word, so this should not match as a company
        assert result is None

    def test_comes_out_of_stealth(self):
        article = _make_article("NovaTech comes out of stealth to challenge AWS")
        result = extract_from_article(article)
        assert result is not None
        assert result.company_name == "NovaTech"


class TestCleanCompanyName:
    def test_strips_publisher_suffix(self):
        assert _clean_company_name("Acme - TechCrunch") == "Acme"

    def test_strips_parenthetical(self):
        assert _clean_company_name("Acme ($10M funding)") == "Acme"

    def test_handles_plain_name(self):
        assert _clean_company_name("Acme") == "Acme"

    def test_strips_html(self):
        assert _clean_company_name("<b>Acme</b>") == "Acme"


class TestLooksLikeCompany:
    def test_valid_names(self):
        assert _looks_like_company("Acme")
        assert _looks_like_company("Deep Tech AI")

    def test_rejects_stop_words(self):
        assert not _looks_like_company("the")
        assert not _looks_like_company("how to do things")

    def test_rejects_empty(self):
        assert not _looks_like_company("")
        assert not _looks_like_company("a")

    def test_rejects_long_sentence(self):
        assert not _looks_like_company("this is a very long sentence that is not a company")

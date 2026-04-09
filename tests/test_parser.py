"""Tests for signal parsing and company mention extraction."""

from datetime import datetime, timezone

from src.models.signal import SignalType
from src.sources.parser import ParsedMention, extract_mentions, _detect_signal_type
from src.sources.twitter_api import FetchedTweet


def _make_tweet(content: str) -> FetchedTweet:
    return FetchedTweet(
        tweet_id="test123",
        author="testuser",
        content=content,
        url="https://x.com/testuser/status/test123",
        published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )


class TestSignalTypeDetection:
    def test_funding_raised(self):
        assert _detect_signal_type("Acme raised $5M in seed funding") == SignalType.FUNDING

    def test_funding_series(self):
        assert _detect_signal_type("Series A round announced for $20M") == SignalType.FUNDING

    def test_funding_dollar_amount(self):
        assert _detect_signal_type("$10M funding round closed") == SignalType.FUNDING

    def test_launch(self):
        assert _detect_signal_type("We just launched our product today") == SignalType.PRODUCT_LAUNCH

    def test_launch_now_live(self):
        assert _detect_signal_type("Our new tool is now live and available") == SignalType.PRODUCT_LAUNCH

    def test_yc_batch(self):
        assert _detect_signal_type("Proud to be part of YC W26 batch") == SignalType.X_MENTION

    def test_product_shipped(self):
        assert _detect_signal_type("We shipped our new v2 update") == SignalType.PRODUCT_LAUNCH

    def test_hiring(self):
        assert _detect_signal_type("We're hiring engineers, join our team") == SignalType.HIRING_SURGE

    def test_acquisition(self):
        assert _detect_signal_type("BigCo acquired SmallStartup") == SignalType.OTHER

    def test_no_category(self):
        assert _detect_signal_type("Beautiful day for a walk in the park") == SignalType.X_MENTION


class TestMentionExtraction:
    def test_at_mention_extraction(self):
        tweet = _make_tweet("Congrats to @AcmeAI on their launch!")
        mentions = extract_mentions(tweet)
        names = [m.company_name for m in mentions]
        assert "AcmeAI" in names

    def test_company_action_pattern(self):
        tweet = _make_tweet("Acme Corp raised $5M in seed funding today")
        mentions = extract_mentions(tweet)
        names = [m.company_name for m in mentions]
        assert any("Acme" in name for name in names)

    def test_congrats_pattern(self):
        tweet = _make_tweet("Congrats to Skyline Labs on the Series A!")
        mentions = extract_mentions(tweet)
        names = [m.company_name for m in mentions]
        assert any("Skyline" in name for name in names)

    def test_stopwords_filtered(self):
        tweet = _make_tweet("The new startup is launching today")
        mentions = extract_mentions(tweet)
        names = [m.company_name.lower() for m in mentions]
        assert "the" not in names
        assert "new" not in names

    def test_category_attached_to_mentions(self):
        tweet = _make_tweet("@AcmeAI raised $10M in Series A funding")
        mentions = extract_mentions(tweet)
        assert len(mentions) > 0
        assert mentions[0].signal_type == SignalType.FUNDING

    def test_deduplication(self):
        tweet = _make_tweet(
            "Congrats to @AcmeAI! @AcmeAI just launched an amazing product."
        )
        mentions = extract_mentions(tweet)
        names = [m.company_name for m in mentions]
        assert names.count("AcmeAI") == 1

    def test_url_extraction(self):
        tweet = _make_tweet(
            "Check out @AcmeAI at https://acmeai.com - they just launched!"
        )
        mentions = extract_mentions(tweet)
        acme = [m for m in mentions if m.company_name == "AcmeAI"]
        assert len(acme) == 1
        assert acme[0].company_url == "https://acmeai.com"

    def test_multiple_companies(self):
        tweet = _make_tweet(
            "@AlphaAI and @BetaTech both launched today at ProductHunt"
        )
        mentions = extract_mentions(tweet)
        names = [m.company_name for m in mentions]
        assert "AlphaAI" in names
        assert "BetaTech" in names

    def test_empty_content(self):
        tweet = _make_tweet("")
        mentions = extract_mentions(tweet)
        assert mentions == []

    def test_no_companies(self):
        tweet = _make_tweet("Beautiful day for a walk in the park")
        mentions = extract_mentions(tweet)
        assert len(mentions) == 0


class TestMentionContext:
    def test_context_includes_surrounding_text(self):
        tweet = _make_tweet(
            "Big news! @AcmeAI raised $5M in seed funding. Congrats to the team!"
        )
        mentions = extract_mentions(tweet)
        acme = [m for m in mentions if m.company_name == "AcmeAI"]
        assert len(acme) == 1
        assert "raised" in acme[0].context or "AcmeAI" in acme[0].context

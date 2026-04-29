from argus.core.dedup import filter_unseen, is_seen, make_fingerprint, mark_seen


def test_make_fingerprint_stable():
    fp1 = make_fingerprint("news_watch", "https://example.com/article")
    fp2 = make_fingerprint("news_watch", "https://example.com/article")
    assert fp1 == fp2
    assert len(fp1) == 64


def test_make_fingerprint_different_workflows():
    fp1 = make_fingerprint("news_watch", "same-id")
    fp2 = make_fingerprint("job_watch", "same-id")
    assert fp1 != fp2


def test_is_seen_false_initially():
    fp = make_fingerprint("news_watch", "https://new-article.com")
    assert is_seen(fp) is False


def test_mark_seen_and_is_seen():
    fp = make_fingerprint("news_watch", "https://example.com/article2")
    mark_seen(fp, "news_watch", "news_article", source_url="https://example.com/article2")
    assert is_seen(fp) is True


def test_mark_seen_idempotent():
    fp = make_fingerprint("news_watch", "https://example.com/article3")
    mark_seen(fp, "news_watch", "news_article")
    mark_seen(fp, "news_watch", "news_article")  # second call should not raise
    assert is_seen(fp) is True


def test_filter_unseen_removes_seen_items():
    fp = make_fingerprint("news_watch", "https://seen.com")
    mark_seen(fp, "news_watch", "news_article")

    items = [
        {"url": "https://seen.com", "title": "already seen"},
        {"url": "https://new.com", "title": "new article"},
    ]
    unseen = filter_unseen(items, "news_watch", "url")

    assert len(unseen) == 1
    assert unseen[0]["url"] == "https://new.com"
    assert "_fingerprint" in unseen[0]


def test_filter_unseen_all_new():
    items = [
        {"url": "https://a.com", "title": "A"},
        {"url": "https://b.com", "title": "B"},
    ]
    unseen = filter_unseen(items, "news_watch", "url")
    assert len(unseen) == 2

from campusos.digest import Digest, render_digest


def _sample_item(idx: int, **overrides) -> dict:
    base = {
        "title": f"Software Intern {idx}",
        "company": f"Northwind {idx}",
        "location_raw": "Bengaluru",
        "seniority": "intern",
        "score": 0.9 - idx * 0.02,
        "reasons": ["Python matched", "SQL matched", "Eligible grad year", "Extra reason"],
        "deadline": "2026-12-10",
        "deadline_evidence": "Apply before 2026-12-10.",
        "apply_url": f"https://northwind{idx}.example/jobs/{idx}",
        "flags": [],
        "is_new": True,
        "is_changed": False,
    }
    base.update(overrides)
    return base


def test_digest_normal_and_sections():
    items = [
        _sample_item(1, is_new=True, is_changed=False, score=0.92),
        _sample_item(2, is_new=False, is_changed=True, score=0.81, flags=["domain_mismatch"]),
    ]
    digest = render_digest(
        items,
        profile_label="profile_a_tech",
        run={"started_at": "2026-11-28T10:00:00Z"},
        review_count=3,
        coverage={"sources_checked": 6, "listings_found": 42, "after_dedup": 18},
    )
    assert isinstance(digest, Digest)
    assert "2026-11-28" in digest.subject
    assert "2 matches" in digest.subject
    assert "New (1)" in digest.text
    assert "Changed (1)" in digest.text
    assert "Needs your review (3)" in digest.text
    assert "Checked 6 sources, 42 listings, 18 candidates" in digest.text
    assert "CampusOS never applies on your behalf. Review every link yourself." in digest.text
    assert "92% match" in digest.text
    assert "domain_mismatch" in digest.text
    assert "Extra reason" not in digest.text  # top 3 reasons only
    assert "Northwind 1" in digest.html and "Northwind 2" in digest.html


def test_digest_empty_and_missing_fields():
    empty = render_digest([], profile_label="profile_a_tech", run={"date": "2026-11-28"})
    assert "no new matches this run" in empty.subject
    assert "no new matches this run" in empty.text
    assert "no new matches this run" in empty.html

    sparse = render_digest([{}], profile_label="profile_a_tech", run={})
    assert "unknown" in sparse.text
    assert "unknown" in sparse.html


def test_digest_caps_at_15_and_sorts_desc():
    items = [_sample_item(i, score=i / 25.0) for i in range(1, 21)]
    digest = render_digest(items, profile_label="profile_a_tech", run={"date": "2026-11-28"})
    assert "15 matches" in digest.subject
    assert "Software Intern 20" in digest.text
    assert "Software Intern 5" not in digest.text
    assert digest.text.index("Software Intern 20") < digest.text.index("Software Intern 19")


def test_digest_escapes_xss_and_blocks_non_http_links():
    items = [
        _sample_item(
            1,
            title="<script>alert(1)</script>",
            apply_url="javascript:alert(1)",
            flags=["hidden_content"],
        )
    ]
    digest = render_digest(items, profile_label="profile_a_tech", run={"date": "2026-11-28"})
    assert "<script>" not in digest.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in digest.html
    assert 'href="javascript:' not in digest.html
    assert "javascript:alert(1)" in digest.html
    assert "hidden_content" in digest.html
    assert "rel=\"noopener noreferrer\"" not in digest.html  # no anchor for javascript:


def test_digest_deterministic():
    items = [_sample_item(1)]
    d1 = render_digest(items, profile_label="p", run={"date": "2026-11-28"})
    d2 = render_digest(items, profile_label="p", run={"date": "2026-11-28"})
    assert d1 == d2

import datetime
import pytest

from campusos.ics import build_ics

FIXED_NOW = datetime.datetime(2026, 11, 28, 10, 0, 0, tzinfo=datetime.timezone.utc)


def _unfold(ics_text: str) -> str:
    return ics_text.replace("\r\n ", "")


def test_ics_structure_and_crlf():
    out = build_ics(
        uid_key="northwind-swe-1",
        title="Backend Engineer Intern",
        company="Northwind Systems",
        deadline=datetime.date(2026, 12, 10),
        apply_url="https://northwind.example/jobs/1",
        evidence="Applications close on December 10, 2026.",
        profile_label="profile_a_tech",
        now=FIXED_NOW,
    )
    assert out.endswith("\r\n")
    assert "\n" not in out.replace("\r\n", "")
    assert "BEGIN:VCALENDAR\r\n" in out
    assert "VERSION:2.0\r\n" in out
    assert "PRODID:" in out
    assert "CALSCALE:GREGORIAN\r\n" in out
    assert "BEGIN:VEVENT\r\n" in out
    assert "UID:northwind-swe-1@campusos.invalid\r\n" in out
    assert "DTSTART;VALUE=DATE:20261210\r\n" in out
    assert "DTEND;VALUE=DATE:20261211\r\n" in out
    assert "DTSTAMP:20261128T100000Z\r\n" in out
    assert "TRIGGER:-P3D\r\n" in out
    assert "TRIGGER:-P1D\r\n" in out
    assert out.count("BEGIN:VALARM\r\n") == 2
    assert "END:VEVENT\r\nEND:VCALENDAR\r\n" in out


def test_ics_line_folding_75_octets_and_non_ascii():
    out = build_ics(
        uid_key="uk-role-1",
        title="Quantitative Analyst — £50,000 Café & Résumé Systems " + ("x" * 60),
        company="Boreal Capital Ltd",
        deadline=datetime.date(2026, 12, 15),
        apply_url="https://boreal.example/careers/42",
        evidence="Salary £50,000 per annum; apply by 15 Dec.",
        profile_label="profile_b_finance",
        now=FIXED_NOW,
    )
    for line in out.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    unfolded = _unfold(out)
    assert "£50,000".replace(",", "\\,") in unfolded
    assert "Café" in unfolded
    assert "Résumé" in unfolded


def test_ics_escaping_and_injection_prevention():
    out = build_ics(
        uid_key="inj-1",
        title="Intern\r\nBEGIN:VALARM\r\nATTENDEE:mailto:evil@attacker.invalid\r\nEND:VEVENT",
        company="Acme; Corp, Inc\\HQ",
        deadline=datetime.date(2026, 12, 5),
        apply_url="https://acme.example/apply",
        evidence="Due Dec 5.\r\nEND:VEVENT\r\nATTENDEE:evil@attacker.invalid",
        profile_label="profile_a_tech",
        now=FIXED_NOW,
    )
    unfolded = _unfold(out)
    lines = unfolded.split("\r\n")
    assert sum(1 for ln in lines if ln == "BEGIN:VALARM") == 2
    assert sum(1 for ln in lines if ln == "END:VEVENT") == 1
    assert not any(ln.startswith("ATTENDEE:") for ln in lines)
    assert "Acme\\; Corp\\, Inc\\\\HQ" in unfolded


def test_ics_rejects_past_deadline_and_bad_urls():
    with pytest.raises(ValueError):
        build_ics(
            uid_key="past-1",
            title="Old Role",
            company="Northwind",
            deadline=datetime.date(2026, 11, 20),
            apply_url="https://northwind.example/1",
            evidence=None,
            profile_label="profile_a_tech",
            now=FIXED_NOW,
        )

    for bad_url in ("javascript:alert(1)", "ftp://northwind.example/1", "https://bad.example/a\nb"):
        with pytest.raises(ValueError):
            build_ics(
                uid_key="bad-url",
                title="Role",
                company="Northwind",
                deadline=datetime.date(2026, 12, 1),
                apply_url=bad_url,
                evidence=None,
                profile_label="profile_a_tech",
                now=FIXED_NOW,
            )


def test_ics_is_deterministic():
    kwargs = dict(
        uid_key="det-1",
        title="Data Intern",
        company="Northwind",
        deadline=datetime.date(2026, 12, 20),
        apply_url="https://northwind.example/data",
        evidence="Apply by Dec 20.",
        profile_label="profile_a_tech",
        now=FIXED_NOW,
    )
    assert build_ics(**kwargs) == build_ics(**kwargs)

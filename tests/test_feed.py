"""`feed.py` testai — be Home Assistant (modulis įkeliamas tiesiai iš failo)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

_PATH = Path(__file__).parents[1] / "custom_components" / "atlieku_grafikas" / "feed.py"
_spec = importlib.util.spec_from_file_location("atlieku_grafikas_feed", _PATH)
feed = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = feed
_spec.loader.exec_module(feed)

TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcde"


@pytest.mark.parametrize(
    "url",
    [
        f"https://api.example.lt/api/cal/{TOKEN}.ics",
        f"https://api.example.lt/api/cal/{TOKEN}.json",
        f"webcal://api.example.lt/api/cal/{TOKEN}.ics",
        f"  https://api.example.lt/api/cal/{TOKEN}.ics?x=1  ",
    ],
)
def test_nuoroda_normalizuojama_i_json(url: str) -> None:
    parsed = feed.parse_feed_url(url)
    assert parsed.json_url == f"https://api.example.lt/api/cal/{TOKEN}.json"
    # Santrauka, ne pats raktas.
    assert TOKEN not in parsed.token_hash
    assert len(parsed.token_hash) == 16


def test_ta_pati_nuoroda_ta_pati_santrauka() -> None:
    a = feed.parse_feed_url(f"webcal://x.lt/api/cal/{TOKEN}.ics")
    b = feed.parse_feed_url(f"https://x.lt/api/cal/{TOKEN}.json")
    assert a.token_hash == b.token_hash


@pytest.mark.parametrize(
    "url",
    ["", "labas", "ftp://x.lt/api/cal/abc.ics", "https://x.lt/kitas/kelias.ics", "https://x.lt/api/cal/trumpas.ics"],
)
def test_netinkama_nuoroda(url: str) -> None:
    with pytest.raises(feed.InvalidFeedUrl):
        feed.parse_feed_url(url)


SAMPLE = {
    "version": 1,
    "today": "2026-10-11",
    "language": "lt",
    "pro": True,
    "address": {"label": "Vilniaus g. 5, Bajorai", "settlement": "Bajorai", "street": "Vilniaus g.", "houseNumber": "5"},
    "wasteTypes": [
        {"code": "glass", "name": "Stiklas", "nextDate": "2026-10-20", "daysUntil": 9,
         "dates": ["2026-11-17", "2026-10-20"], "providers": ["Ekonovus"]},
        {"code": "mixed", "name": "Mišrios", "nextDate": "2026-10-14", "daysUntil": 3,
         "dates": ["2026-10-14", "2026-10-28"], "providers": ["Ecoservice"], "naujasLaukas": 1},
    ],
}


def test_isskaidymas() -> None:
    f = feed.parse_feed(SAMPLE)
    assert f.pro
    assert f.address.label == "Vilniaus g. 5, Bajorai"
    assert f.address.house_number == "5"
    glass = f.by_code()["glass"]
    # Datos surikiuojamos nepriklausomai nuo atsakymo tvarkos.
    assert glass.dates == (date(2026, 10, 20), date(2026, 11, 17))
    assert glass.providers == ("Ekonovus",)


def test_praejusios_datos_iskrenta_vietoje() -> None:
    mixed = feed.parse_feed(SAMPLE).by_code()["mixed"]
    assert mixed.next_date(date(2026, 10, 14)) == date(2026, 10, 14)
    assert mixed.next_date(date(2026, 10, 15)) == date(2026, 10, 28)
    assert mixed.next_date(date(2026, 10, 29)) is None
    assert feed.days_until(mixed.next_date(date(2026, 10, 11)), date(2026, 10, 11)) == 3


def test_naujesne_versija_atmetama() -> None:
    with pytest.raises(feed.UnsupportedFeedVersion):
        feed.parse_feed({**SAMPLE, "version": feed.SUPPORTED_VERSION + 1})


def test_be_pro_tuscias() -> None:
    f = feed.parse_feed({**SAMPLE, "pro": False, "wasteTypes": []})
    assert not f.pro
    assert f.waste_types == ()


def test_paros_minute_pastovi_ir_pasiskirsto() -> None:
    a = feed.parse_feed_url(f"https://x.lt/api/cal/{TOKEN}.json").token_hash
    assert feed.sync_slot(a) == feed.sync_slot(a)
    assert 0 <= feed.sync_slot(a) < feed.MINUTES_PER_DAY

    # 2000 atsitiktinių raktų — kiekviena paros valanda gauna savo dalį.
    import hashlib
    slots = [feed.sync_slot(hashlib.sha256(str(i).encode()).hexdigest()[:16]) for i in range(2000)]
    per_hour = [sum(1 for s in slots if s // 60 == h) for h in range(24)]
    assert min(per_hour) > 2000 / 24 / 2


def test_iki_kito_savo_laiko() -> None:
    now = datetime(2026, 10, 11, 10, 0, tzinfo=UTC)
    # Savo laikas — 20:00: šiandien, po 10 val.
    assert feed.next_sync_delay(now, 20 * 60) == timedelta(hours=10)
    # 13:00 — per arti (mažiau nei 6 val.), tad rytoj.
    assert feed.next_sync_delay(now, 13 * 60) == timedelta(hours=27)
    # 05:00 — jau praėjo, tad rytoj.
    assert feed.next_sync_delay(now, 5 * 60) == timedelta(hours=19)

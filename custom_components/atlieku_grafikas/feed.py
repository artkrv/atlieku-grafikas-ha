"""Atliekų grafiko feed'as: nuorodos normalizavimas ir JSON išskaidymas.

Šis modulis SĄMONINGAI neimportuoja Home Assistant — jį galima testuoti be HA.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

# Palaikomas JSON formato versijos numeris (`version` lauke). Serveris jį didina tik
# keisdamas formatą nesuderinamai.
SUPPORTED_VERSION = 1

_TOKEN_PATH = re.compile(r"^(?P<prefix>.*/cal/)(?P<token>[A-Za-z0-9_-]{20,})\.(?:ics|json)$")


class InvalidFeedUrl(ValueError):
    """Nuoroda nėra Atliekų grafiko kalendoriaus nuoroda."""


@dataclass(frozen=True)
class FeedUrl:
    """Normalizuota nuoroda: JSON adresas ir rakto santrauka unikaliam ID."""

    json_url: str
    token_hash: str


def parse_feed_url(raw: str) -> FeedUrl:
    """Priima programėlės nuorodą bet kuriuo pavidalu ir grąžina JSON adresą.

    Tinka `.ics` ir `.json`, `https://`, `http://` ir `webcal://` — naudotojas įklijuos
    tai, ką nukopijavo, o kalendoriui skirta nuoroda dažniausiai būna `webcal://…ics`.
    """
    text = (raw or "").strip()
    if not text:
        raise InvalidFeedUrl("empty")

    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme == "webcal":
        scheme = "https"
    if scheme not in ("http", "https") or not parts.netloc:
        raise InvalidFeedUrl("scheme")

    match = _TOKEN_PATH.match(parts.path)
    if match is None:
        raise InvalidFeedUrl("path")

    token = match["token"]
    path = f"{match['prefix']}{token}.json"
    json_url = urlunsplit((scheme, parts.netloc, path, "", ""))

    # Unikalus ID — santrauka, ne pats raktas: jis matomas HA registruose ir derinimo
    # išklotinėse, o raktas yra prieigos slaptažodis.
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
    return FeedUrl(json_url=json_url, token_hash=token_hash)


@dataclass(frozen=True)
class WasteSchedule:
    """Vienos rūšies būsimi išvežimai."""

    code: str
    name: str
    dates: tuple[date, ...]
    providers: tuple[str, ...] = ()

    def upcoming(self, today: date) -> tuple[date, ...]:
        """Datos nuo šiandien — tarp atnaujinimų praėjusios iškrenta vietoje."""
        return tuple(d for d in self.dates if d >= today)

    def next_date(self, today: date) -> date | None:
        upcoming = self.upcoming(today)
        return upcoming[0] if upcoming else None


@dataclass(frozen=True)
class Address:
    label: str
    settlement: str
    street: str | None = None
    house_number: str | None = None


@dataclass(frozen=True)
class Feed:
    version: int
    language: str
    pro: bool
    address: Address
    waste_types: tuple[WasteSchedule, ...] = field(default_factory=tuple)

    def by_code(self) -> dict[str, WasteSchedule]:
        return {w.code: w for w in self.waste_types}


class UnsupportedFeedVersion(ValueError):
    """Serveris grąžino naujesnį formatą, nei moka ši integracijos versija."""


def parse_feed(data: dict[str, Any]) -> Feed:
    """JSON → `Feed`. Nežinomi laukai ignoruojami, trūkstami privalomi — klaida."""
    version = int(data.get("version", 0))
    if version > SUPPORTED_VERSION:
        raise UnsupportedFeedVersion(str(version))

    address = data["address"]
    waste_types = tuple(
        WasteSchedule(
            code=str(w["code"]),
            name=str(w.get("name") or w["code"]),
            dates=tuple(sorted(date.fromisoformat(d) for d in w.get("dates", []))),
            providers=tuple(str(p) for p in w.get("providers", [])),
        )
        for w in data.get("wasteTypes", [])
    )

    return Feed(
        version=version,
        language=str(data.get("language", "lt")),
        pro=bool(data.get("pro", False)),
        address=Address(
            label=str(address.get("label") or address.get("settlement") or ""),
            settlement=str(address.get("settlement") or ""),
            street=address.get("street"),
            house_number=address.get("houseNumber"),
        ),
        waste_types=waste_types,
    )


def days_until(target: date | None, today: date) -> int | None:
    return None if target is None else (target - today).days


MINUTES_PER_DAY = 24 * 60

# Mažiausias tarpas iki kito atnaujinimo. Be jo įrašas, pridėtas ar perkrautas prieš pat
# savo laiką, kreiptųsi du kartus iš eilės.
MIN_SYNC_GAP = timedelta(hours=6)


def sync_slot(token_hash: str) -> int:
    """Paros minutė (UTC), kada šis adresas atnaujinamas.

    Iš rakto santraukos, ne atsitiktinė: pastovi tarp perkrovimų, o skirtingi adresai
    tolygiai pasiskirsto per parą — 50 tūkst. adresų ≈ 35 užklausos per minutę, ne visos
    vienu metu.
    """
    return int(token_hash[:8], 16) % MINUTES_PER_DAY


def next_sync_delay(now_utc: datetime, slot_minute: int) -> timedelta:
    """Kiek laukti iki kito savo laiko (ne anksčiau nei po `MIN_SYNC_GAP`)."""
    midnight = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    target = midnight + timedelta(minutes=slot_minute)
    while target - now_utc < MIN_SYNC_GAP:
        target += timedelta(days=1)
    return target - now_utc

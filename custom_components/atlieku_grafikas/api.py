"""HTTP klientas Atliekų grafiko feed'ui."""

from __future__ import annotations

import asyncio
from http import HTTPStatus

import aiohttp

from .feed import Feed, UnsupportedFeedVersion, parse_feed

REQUEST_TIMEOUT = 30


class FeedError(Exception):
    """Bendra feed'o klaida."""


class FeedConnectionError(FeedError):
    """Serveris nepasiekiamas arba atsakė klaida — laikina."""


class FeedNotFound(FeedError):
    """Nuoroda nebegalioja: sinchronizacija išjungta programėlėje arba adresas ištrintas."""


class AtliekuGrafikasClient:
    """Skaito vieno adreso JSON feed'ą."""

    def __init__(self, session: aiohttp.ClientSession, json_url: str) -> None:
        self._session = session
        self._url = json_url
        # Paskutinis gautas atsakymas — nepasikeitus grafikui serveris grąžina 304 be turinio.
        self._etag: str | None = None
        self._feed: Feed | None = None

    async def async_get_feed(self) -> Feed:
        headers = {"Accept": "application/json"}
        if self._etag and self._feed is not None:
            headers["If-None-Match"] = self._etag

        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.get(self._url, headers=headers) as response,
            ):
                if response.status == HTTPStatus.NOT_MODIFIED and self._feed is not None:
                    return self._feed
                if response.status == HTTPStatus.NOT_FOUND:
                    raise FeedNotFound
                if response.status != HTTPStatus.OK:
                    raise FeedConnectionError(f"HTTP {response.status}")
                data = await response.json(content_type=None)
                etag = response.headers.get("ETag")
        except FeedError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FeedConnectionError(str(err)) from err

        try:
            feed = parse_feed(data)
        except UnsupportedFeedVersion:
            # Atskirai — naudotojui reikia atnaujinti integraciją, o ne laukti.
            raise
        except (KeyError, TypeError, ValueError) as err:
            raise FeedError(f"Netinkamas atsakymas: {err}") from err

        self._etag, self._feed = etag, feed
        return feed

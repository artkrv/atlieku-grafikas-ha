"""Duomenų koordinatorius — viena užklausa visiems adreso entity."""

from __future__ import annotations

import logging

from homeassistant.util import dt as dt_util

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AtliekuGrafikasClient, FeedError, FeedNotFound
from .const import DOMAIN, RETRY_INTERVAL
from .feed import Feed, UnsupportedFeedVersion, next_sync_delay, sync_slot

_LOGGER = logging.getLogger(__name__)

type AtliekuGrafikasConfigEntry = ConfigEntry[AtliekuGrafikasCoordinator]


class AtliekuGrafikasCoordinator(DataUpdateCoordinator[Feed]):
    """Atnaujina kartą per parą savo laiku; nepavykus — po valandos.

    Kito atnaujinimo laikas perskaičiuojamas po KIEKVIENO bandymo (`update_interval`
    keičiamas `_async_update_data` viduje): koordinatorius naudoja jį planuodamas kitą
    kartą, tad intervalas nuolat taikosi į tą pačią paros minutę ir nedreifuoja.
    """

    config_entry: AtliekuGrafikasConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: AtliekuGrafikasConfigEntry,
        client: AtliekuGrafikasClient,
    ) -> None:
        self._slot = sync_slot(str(entry.unique_id))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=next_sync_delay(dt_util.utcnow(), self._slot),
        )
        self._client = client
        # Rūšių pavadinimai HA kalba (kalendoriui ir atributams). Užpildo
        # `async_setup_entry`; pakeitus HA kalbą, atsinaujina perkrovus integraciją.
        self.waste_names: dict[str, str] = {}

    def waste_name(self, code: str, fallback: str) -> str:
        """Rūšies pavadinimas HA kalba; nežinomai rūšiai — serverio."""
        return self.waste_names.get(code, fallback)

    async def _async_update_data(self) -> Feed:
        # Nepavykus lieka trumpas intervalas; pavykus — iki kito savo laiko.
        self.update_interval = RETRY_INTERVAL
        feed = await self._fetch()
        self.update_interval = next_sync_delay(dt_util.utcnow(), self._slot)
        return feed

    async def _fetch(self) -> Feed:
        try:
            return await self._client.async_get_feed()
        except FeedNotFound as err:
            # Nuolatinė būsena, ne laikina klaida: naudotojas išjungė sinchronizaciją
            # programėlėje (ar ištrynė adresą). Kartoti neverta — HA paleidžia reauth
            # srautą, kuriame įklijuojama nauja nuoroda.
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="feed_not_found"
            ) from err
        except UnsupportedFeedVersion as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="unsupported_version"
            ) from err
        except FeedError as err:
            raise UpdateFailed(str(err)) from err

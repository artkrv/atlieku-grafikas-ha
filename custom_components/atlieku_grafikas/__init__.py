"""Atliekų grafikas — išvežimų grafikas Home Assistant'e."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.translation import async_get_translations

from .api import AtliekuGrafikasClient
from .const import CONF_URL, DOMAIN, TRANSLATED_WASTE_TYPES
from .coordinator import AtliekuGrafikasConfigEntry, AtliekuGrafikasCoordinator
from .feed import parse_feed_url

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: AtliekuGrafikasConfigEntry) -> bool:
    """Vienas config entry — vienas adresas."""
    client = AtliekuGrafikasClient(
        async_get_clientsession(hass), parse_feed_url(entry.data[CONF_URL]).json_url
    )
    coordinator = AtliekuGrafikasCoordinator(hass, entry, client)

    # Tie patys vertimai, kuriuos HA naudoja jutiklių pavadinimams — kad kalendoriuje ir
    # atributuose rūšys vadintųsi taip pat, o ne programėlės kalba.
    translations = await async_get_translations(hass, hass.config.language, "entity", {DOMAIN})
    prefix = f"component.{DOMAIN}.entity.sensor."
    coordinator.waste_names = {
        code: name
        for code in TRANSLATED_WASTE_TYPES
        if (name := translations.get(f"{prefix}{code}.name"))
    }
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AtliekuGrafikasConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

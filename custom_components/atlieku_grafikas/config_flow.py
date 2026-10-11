"""Konfigūracija: naudotojas įklijuoja nuorodą iš programėlės."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import AtliekuGrafikasClient, FeedConnectionError, FeedError, FeedNotFound
from .const import CONF_URL, DOMAIN
from .feed import Feed, InvalidFeedUrl, UnsupportedFeedVersion, parse_feed_url

# `voluptuous`, ne `probatio`: nuo HA 2026.10 vardas nukreipiamas į probatio, o
# senesnėse versijose veikia kaip buvo — integracija tinka abiem.
URL_SCHEMA = vol.Schema(
    {vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL))}
)


class AtliekuGrafikasConfigFlow(ConfigFlow, domain=DOMAIN):
    """Vienas įrašas — vienas adresas. Keli adresai — integracija pridedama kelis kartus."""

    VERSION = 1

    async def _validate(self, url: str) -> tuple[str, Feed | None, dict[str, str]]:
        """Grąžina rakto santrauką, feed'ą ir klaidas formai."""
        try:
            parsed = parse_feed_url(url)
        except InvalidFeedUrl:
            return "", None, {CONF_URL: "invalid_url"}

        client = AtliekuGrafikasClient(async_get_clientsession(self.hass), parsed.json_url)
        try:
            feed = await client.async_get_feed()
        except FeedNotFound:
            return parsed.token_hash, None, {CONF_URL: "not_found"}
        except UnsupportedFeedVersion:
            return parsed.token_hash, None, {"base": "unsupported_version"}
        except FeedConnectionError:
            return parsed.token_hash, None, {"base": "cannot_connect"}
        except FeedError:
            return parsed.token_hash, None, {"base": "unknown"}

        # Be Pro feed'as galioja, bet tuščias — pridėtas atrodytų kaip sugedęs.
        if not feed.pro:
            return parsed.token_hash, None, {"base": "not_pro"}

        return parsed.token_hash, feed, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            token_hash, feed, errors = await self._validate(user_input[CONF_URL])
            if feed is not None:
                await self.async_set_unique_id(token_hash)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=feed.address.label,
                    data={CONF_URL: user_input[CONF_URL].strip()},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(URL_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Nuoroda nebegalioja — sinchronizacija išjungta ir įjungta iš naujo programėlėje."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            token_hash, feed, errors = await self._validate(user_input[CONF_URL])
            if feed is not None:
                # Nauja nuoroda gali būti kitam adresui — tada tai ne pakeitimas, o
                # naujas įrašas, ir jį reikia pridėti atskirai.
                if feed.address.label != entry.title:
                    errors = {CONF_URL: "different_address"}
                else:
                    await self.async_set_unique_id(token_hash)
                    self._abort_if_unique_id_configured()
                    return self.async_update_reload_and_abort(
                        entry,
                        unique_id=token_hash,
                        data_updates={CONF_URL: user_input[CONF_URL].strip()},
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=URL_SCHEMA,
            description_placeholders={"address": entry.title},
            errors=errors,
        )

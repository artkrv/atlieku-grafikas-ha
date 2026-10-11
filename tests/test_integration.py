"""Integracija su tikru Home Assistant (pytest-homeassistant-custom-component)."""

from __future__ import annotations

from datetime import date, timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.atlieku_grafikas.const import CONF_URL, DOMAIN, RETRY_INTERVAL
from custom_components.atlieku_grafikas.feed import parse_feed_url

TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcde"
ICS_URL = f"webcal://api.example.lt/api/cal/{TOKEN}.ics"
JSON_URL = f"https://api.example.lt/api/cal/{TOKEN}.json"
TODAY = date(2026, 10, 11)


def payload(pro: bool = True, label: str = "Vilniaus g. 5, Bajorai") -> dict:
    return {
        "version": 1,
        "today": TODAY.isoformat(),
        "language": "lt",
        "pro": pro,
        "address": {"label": label, "settlement": "Bajorai", "street": "Vilniaus g.", "houseNumber": "5"},
        "wasteTypes": [
            {"code": "mixed", "name": "Mišrios", "nextDate": "2026-10-14", "daysUntil": 3,
             "dates": ["2026-10-14", "2026-10-28"], "providers": ["Ecoservice"]},
            {"code": "glass", "name": "Stiklas", "nextDate": "2026-10-14", "daysUntil": 3,
             "dates": ["2026-10-14"], "providers": ["Ekonovus"]},
        ] if pro else [],
    }


@pytest.fixture
def frozen(freezer: FrozenDateTimeFactory, hass: HomeAssistant) -> FrozenDateTimeFactory:
    freezer.move_to(dt_util.start_of_local_day(TODAY) + timedelta(hours=10))
    return freezer


async def test_config_flow_sukuria_irasa(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, frozen
) -> None:
    aioclient_mock.get(JSON_URL, json=payload())

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: ICS_URL})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Vilniaus g. 5, Bajorai"
    assert result["result"].unique_id == parse_feed_url(ICS_URL).token_hash


@pytest.mark.parametrize(
    ("url", "mock", "error"),
    [
        ("https://x.lt/ne/ta.ics", None, {CONF_URL: "invalid_url"}),
        (ICS_URL, {"status": 404}, {CONF_URL: "not_found"}),
        (ICS_URL, {"json": payload(pro=False)}, {"base": "not_pro"}),
        (ICS_URL, {"status": 500}, {"base": "cannot_connect"}),
        (ICS_URL, {"json": {**payload(), "version": 99}}, {"base": "unsupported_version"}),
    ],
)
async def test_config_flow_klaidos(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, url, mock, error
) -> None:
    if mock is not None:
        aioclient_mock.get(JSON_URL, **mock)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: url})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == error


async def test_tas_pats_adresas_antra_karta(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, frozen
) -> None:
    aioclient_mock.get(JSON_URL, json=payload())
    MockConfigEntry(domain=DOMAIN, unique_id=parse_feed_url(ICS_URL).token_hash, data={CONF_URL: ICS_URL}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: JSON_URL})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Vilniaus g. 5, Bajorai",
        unique_id=parse_feed_url(ICS_URL).token_hash, data={CONF_URL: ICS_URL},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        key.split(":")[0], DOMAIN, f"{entry.unique_id}_{key.split(':')[1]}"
    )
    assert entity_id is not None, key
    return entity_id


async def test_jutikliai_ir_kalendorius(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, frozen
) -> None:
    aioclient_mock.get(JSON_URL, json=payload())
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    mixed = hass.states.get(_entity(hass, entry, "sensor:mixed"))
    assert mixed.state == "2026-10-14"
    assert mixed.attributes["days_until"] == 3
    assert mixed.attributes["waste_type"] == "mixed"
    assert mixed.attributes["providers"] == ["Ecoservice"]
    assert mixed.attributes["upcoming"] == ["2026-10-14", "2026-10-28"]

    nxt = hass.states.get(_entity(hass, entry, "sensor:next_pickup"))
    assert nxt.state == "2026-10-14"
    assert sorted(nxt.attributes["waste_types"]) == ["glass", "mixed"]

    calendar = hass.states.get(_entity(hass, entry, "calendar:calendar"))
    assert calendar.state == "off"
    assert calendar.attributes["start_time"] == "2026-10-14 00:00:00"


async def test_po_vidurnakcio_perskaiciuojama_be_uzklausos(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, frozen: FrozenDateTimeFactory
) -> None:
    # Pradžia — išvežimo dienos vakaras. Kitas atnaujinimas ne anksčiau nei po
    # `MIN_SYNC_GAP` (6 val.), tad iki vidurnakčio naujos užklausos būti neturi.
    frozen.move_to(dt_util.start_of_local_day(date(2026, 10, 14)) + timedelta(hours=21))
    aioclient_mock.get(JSON_URL, json=payload())
    entry = await _setup(hass)
    calls = aioclient_mock.call_count
    assert hass.states.get(_entity(hass, entry, "sensor:mixed")).state == "2026-10-14"

    # Išvežimo diena praėjo: 10-15 00:00:05.
    frozen.move_to(dt_util.start_of_local_day(date(2026, 10, 15)) + timedelta(seconds=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    mixed = hass.states.get(_entity(hass, entry, "sensor:mixed"))
    assert mixed.state == "2026-10-28"
    assert mixed.attributes["days_until"] == 13
    # Stiklas daugiau išvežimų neturi.
    assert hass.states.get(_entity(hass, entry, "sensor:glass")).state == "unknown"
    assert aioclient_mock.call_count == calls


async def test_atsaukta_nuoroda_paleidzia_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, frozen: FrozenDateTimeFactory
) -> None:
    aioclient_mock.get(JSON_URL, json=payload())
    entry = await _setup(hass)

    aioclient_mock.clear_requests()
    aioclient_mock.get(JSON_URL, status=404)
    # Kitas atnaujinimas — ne vėliau nei po paros su `MIN_SYNC_GAP`.
    frozen.tick(timedelta(hours=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == config_entries.SOURCE_REAUTH for f in flows)

    # Įklijuojama nauja nuoroda tam pačiam adresui.
    new_token = "ZyXwVuTsRqPoNmLkJiHgFeDcBa9876543210_-zyxwv"
    new_json = f"https://api.example.lt/api/cal/{new_token}.json"
    aioclient_mock.get(new_json, json=payload())

    flow = next(f for f in flows if f["context"]["source"] == config_entries.SOURCE_REAUTH)
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {CONF_URL: new_json})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_URL] == new_json
    assert entry.unique_id == parse_feed_url(new_json).token_hash


async def test_atnaujinama_kas_para_nepavykus_po_valandos(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, frozen: FrozenDateTimeFactory
) -> None:
    aioclient_mock.get(JSON_URL, json=payload())
    entry = await _setup(hass)
    coordinator = entry.runtime_data

    # Po sėkmės — iki savo paros minutės, ne mažiau nei 6 val. ir ne daugiau nei para su 6 val.
    assert timedelta(hours=6) <= coordinator.update_interval <= timedelta(hours=30)

    aioclient_mock.clear_requests()
    aioclient_mock.get(JSON_URL, status=500)
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.update_interval == RETRY_INTERVAL

    # Senieji duomenys lieka — jutikliai rodo paskutinį žinomą grafiką.
    assert coordinator.data.by_code()["mixed"].dates


async def test_nepasikeitus_304_naudojami_turimi_duomenys(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, frozen
) -> None:
    aioclient_mock.get(JSON_URL, json=payload(), headers={"ETag": '"abc"'})
    entry = await _setup(hass)
    coordinator = entry.runtime_data

    aioclient_mock.clear_requests()
    aioclient_mock.get(JSON_URL, status=304)
    await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data.address.label == "Vilniaus g. 5, Bajorai"
    assert aioclient_mock.mock_calls[-1][3]["If-None-Match"] == '"abc"'

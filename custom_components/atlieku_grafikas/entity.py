"""Bendra entity bazė: vienas įrenginys — vienas adresas."""

from __future__ import annotations

from datetime import date

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER
from .coordinator import AtliekuGrafikasCoordinator


class AtliekuGrafikasEntity(CoordinatorEntity[AtliekuGrafikasCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: AtliekuGrafikasCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            name=coordinator.data.address.label,
            manufacturer=MANUFACTURER,
            entry_type=DeviceEntryType.SERVICE,
        )

    @staticmethod
    def today() -> date:
        return dt_util.now().date()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Po vidurnakčio pasikeičia „po kiek dienų" ir praėjusi data iškrenta — tam
        # nereikia naujos užklausos, užtenka perskaičiuoti iš turimų duomenų.
        self.async_on_remove(
            async_track_time_change(self.hass, self._midnight, hour=0, minute=0, second=5)
        )

    @callback
    def _midnight(self, _now) -> None:
        self.async_write_ha_state()

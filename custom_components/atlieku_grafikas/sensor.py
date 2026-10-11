"""Jutikliai: artimiausias išvežimas kiekvienai rūšiai ir bendras „kitas išvežimas"."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEFAULT_ICON, WASTE_ICONS
from .coordinator import AtliekuGrafikasConfigEntry, AtliekuGrafikasCoordinator
from .entity import AtliekuGrafikasEntity
from .feed import WasteSchedule, days_until

# Atributuose — tiek artimiausių datų. Visi metai būtų per daug: atributai saugomi
# istorijoje su kiekvienu būsenos pakeitimu.
UPCOMING_IN_ATTRIBUTES = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtliekuGrafikasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_waste_types() -> None:
        # Naujas vežėjas ar rūšis gali atsirasti bet kada (tiekėjas paskelbė grafiką) —
        # jutiklis pridedamas be integracijos perkrovimo.
        new = [code for code in coordinator.data.by_code() if code not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(WasteTypeSensor(coordinator, code) for code in new)

    async_add_entities([NextPickupSensor(coordinator)])
    _add_new_waste_types()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_waste_types))


class WasteTypeSensor(AtliekuGrafikasEntity, SensorEntity):
    """Vienos rūšies artimiausio išvežimo data."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: AtliekuGrafikasCoordinator, code: str) -> None:
        super().__init__(coordinator, code)
        self._code = code
        self._attr_icon = WASTE_ICONS.get(code, DEFAULT_ICON)

    @property
    def _waste(self) -> WasteSchedule | None:
        return self.coordinator.data.by_code().get(self._code)

    @property
    def available(self) -> bool:
        # Rūšis dingo iš grafiko (pvz., sezonas baigėsi) — jutiklis lieka, bet nepasiekiamas.
        return super().available and self._waste is not None

    @property
    def name(self) -> str:
        waste = self._waste
        return waste.name if waste is not None else self._code

    @property
    def native_value(self) -> date | None:
        waste = self._waste
        return waste.next_date(self.today()) if waste is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        waste = self._waste
        if waste is None:
            return {"waste_type": self._code}
        today = self.today()
        upcoming = waste.upcoming(today)
        return {
            "waste_type": self._code,
            "days_until": days_until(upcoming[0] if upcoming else None, today),
            "upcoming": [d.isoformat() for d in upcoming[:UPCOMING_IN_ATTRIBUTES]],
            "providers": list(waste.providers),
        }


class NextPickupSensor(AtliekuGrafikasEntity, SensorEntity):
    """Artimiausias bet kurios rūšies išvežimas — vienai kortelei ar automatizacijai."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_translation_key = "next_pickup"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: AtliekuGrafikasCoordinator) -> None:
        super().__init__(coordinator, "next_pickup")

    def _next(self) -> tuple[date | None, list[WasteSchedule]]:
        today = self.today()
        nexts = [(w.next_date(today), w) for w in self.coordinator.data.waste_types]
        dates = [d for d, _ in nexts if d is not None]
        if not dates:
            return None, []
        first = min(dates)
        return first, [w for d, w in nexts if d == first]

    @property
    def native_value(self) -> date | None:
        return self._next()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        first, wastes = self._next()
        return {
            "days_until": days_until(first, self.today()),
            # Tą pačią dieną gali būti kelios rūšys.
            "waste_types": [w.code for w in wastes],
            "waste_names": [w.name for w in wastes],
        }

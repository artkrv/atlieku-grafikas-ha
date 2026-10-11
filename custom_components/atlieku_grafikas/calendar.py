"""Kalendorius: visi adreso išvežimai kaip visos dienos įvykiai."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import AtliekuGrafikasConfigEntry, AtliekuGrafikasCoordinator
from .entity import AtliekuGrafikasEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AtliekuGrafikasConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AtliekuGrafikasCalendar(entry.runtime_data)])


class AtliekuGrafikasCalendar(AtliekuGrafikasEntity, CalendarEntity):
    _attr_translation_key = "pickups"

    def __init__(self, coordinator: AtliekuGrafikasCoordinator) -> None:
        super().__init__(coordinator, "calendar")

    def _events(self) -> list[CalendarEvent]:
        """Visi įvykiai, surikiuoti pagal datą ir rūšį.

        Visos dienos įvykis — `datetime.date`, pabaiga neįskaitytinai kita diena, kaip
        reikalauja HA. Aprašyme — rūšies kodas ir vežėjai: kodas nepriklauso nuo kalbos,
        tad automatizacijos gali jį tikrinti (`'mixed' in trigger.calendar_event.description`).
        """
        events = [
            CalendarEvent(
                start=d,
                end=d + timedelta(days=1),
                summary=waste.name,
                description="\n".join([waste.code, *waste.providers]),
                uid=f"{waste.code}-{d.isoformat()}",
            )
            for waste in self.coordinator.data.waste_types
            for d in waste.dates
        ]
        events.sort(key=lambda e: (e.start, e.summary))
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Šiandienos (vyksta visą dieną) arba artimiausias būsimas įvykis."""
        today = dt_util.now().date()
        return next((e for e in self._events() if e.end > today), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        # Visos dienos įvykis prasideda vietinį vidurnaktį (HA laiko zona).
        def local_midnight(d: date) -> datetime:
            return dt_util.start_of_local_day(d)

        return [
            e
            for e in self._events()
            if local_midnight(e.end) > start_date and local_midnight(e.start) < end_date
        ]

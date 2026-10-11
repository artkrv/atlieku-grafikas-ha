# Atliekų grafikas — Home Assistant

Atliekų išvežimo grafikas iš programėlės **Atliekų grafikas** jūsų Home Assistant'e:
artimiausio išvežimo jutikliai kiekvienai atliekų rūšiai ir kalendorius automatizacijoms.

*English summary below.*

## Ko reikia

- Programėlės **Atliekų grafikas** Pro.
- Įjungta adreso kalendoriaus sinchronizacija: programėlėje *Nustatymai → Adresai →*
  kalendoriaus ženklas prie adreso.

## Diegimas

### HACS

1. HACS → ⋮ → *Custom repositories* → šios repozitorijos adresas, tipas *Integration*.
2. Įdiekite **Atliekų grafikas** ir perkraukite Home Assistant.

### Rankiniu būdu

Nukopijuokite `custom_components/atlieku_grafikas` į savo `config/custom_components/` ir
perkraukite Home Assistant.

## Konfigūracija

*Nustatymai → Įrenginiai ir paslaugos → Pridėti integraciją → Atliekų grafikas* ir
įklijuokite kalendoriaus nuorodą iš programėlės. Tinka bet kuri jos forma: `webcal://…`,
`https://….ics` ar `https://….json`.

Keli adresai — integraciją pridėkite kelis kartus, po vieną kiekvienam adresui.

Jei programėlėje sinchronizaciją išjungsite ir vėl įjungsite, nuoroda pasikeis — Home
Assistant pats paprašys įklijuoti naują.

## Kas sukuriama

Kiekvienam adresui — įrenginys su:

| Entity | Būsena | Atributai |
| --- | --- | --- |
| `sensor.<adresas>_<rūšis>` (pvz. *Mišrios*) | artimiausio išvežimo data | `waste_type`, `days_until`, `upcoming`, `providers` |
| `sensor.<adresas>_kitas_isvezimas` | artimiausias bet kurios rūšies išvežimas | `days_until`, `waste_types`, `waste_names` |
| `calendar.<adresas>_isvezimai` | visos dienos įvykiai | aprašymo pirma eilutė — rūšies kodas |

Duomenys atnaujinami kartą per parą, kiekvienas adresas savo pastoviu paros laiku (kad
visi naudotojai nesikreiptų vienu metu); nepavykus — po valandos. `days_until` ir
praėjusios datos perskaičiuojamos kiekvieną vidurnaktį be naujos užklausos.

Rūšių kodai: `mixed`, `packaging`, `glass`, `food`, `bio`, `green`, `bulky`.

### Automatizacijos pavyzdys

Pranešimas 19:00 dieną prieš išvežimą:

```yaml
triggers:
  - trigger: calendar
    event: start
    entity_id: calendar.vilniaus_g_5_bajorai_isvezimai
    offset: "-05:00:00"
actions:
  - action: notify.mobile_app_telefonas
    data:
      message: "Rytoj išvežamos: {{ trigger.calendar_event.summary }}"
```

Tik konkrečiai rūšiai — sąlyga pagal kodą (nepriklauso nuo programėlės kalbos):

```yaml
conditions:
  - condition: template
    value_template: "{{ trigger.calendar_event.description.split('\n')[0] == 'mixed' }}"
```

---

## English

Waste collection schedule from the **Atliekų grafikas** app (Lithuania). Requires the app's
Pro and calendar sync enabled for the address (*Settings → Addresses →* calendar icon).
Add the integration and paste the calendar link; add it once per address. Creates a date
sensor per waste type, a *next pickup* sensor and a calendar for automations. The first
line of each calendar event description is the language-independent waste type code.

## Kūrimas

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

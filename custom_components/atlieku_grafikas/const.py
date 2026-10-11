"""Konstantos."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "atlieku_grafikas"
MANUFACTURER = "Atliekų grafikas"

CONF_URL = "url"

# Atnaujinama KARTĄ PER PARĄ, kiekvienas adresas savo laiku (`feed.sync_slot`). Grafikai
# keičiasi retai, o datos ir „po kiek dienų" kas vidurnaktį perskaičiuojami vietoje.
#
# Nepavykus — bandoma po valandos, ne po paros: serverio sutrikimas neturi palikti
# naudotojo be naujų duomenų visą parą.
RETRY_INTERVAL = timedelta(hours=1)

# Rūšies kodas → ikona. Nežinomai — bendra.
WASTE_ICONS: dict[str, str] = {
    "mixed": "mdi:trash-can",
    "packaging": "mdi:recycle",
    "plastic": "mdi:bottle-soda-classic",
    "paper": "mdi:newspaper-variant",
    "glass": "mdi:bottle-wine",
    "food": "mdi:food-apple",
    "bio": "mdi:leaf",
    "green": "mdi:leaf",
    "textile": "mdi:tshirt-crew",
    "bulky": "mdi:sofa",
}
DEFAULT_ICON = "mdi:delete-empty"

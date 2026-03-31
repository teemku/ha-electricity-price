"""Constants for the Electricity Price integration."""

VENDOR = "teemku"
INTEGRATION_NAME = "electricity_price"
DOMAIN = INTEGRATION_NAME
PLATFORMS = ["sensor"]

# Config entry keys (stored in entry.data — not user-editable after setup)
CONF_API_KEY = "api_key"
CONF_PRICE_AREA = "price_area"

# Options keys (stored in entry.options — editable via options flow)
CONF_VAT = "vat_percent"
CONF_TRANSFER_FEE = "transfer_fee"
CONF_THRESHOLDS = "thresholds"

# Defaults
DEFAULT_VAT = 0.0
DEFAULT_TRANSFER_FEE = 0.0
DEFAULT_THRESHOLDS = [
    {"name": "Cheap", "below": 5.0, "color": "#22c55e"},
    {"name": "Normal", "below": 12.0, "color": "#f59e0b"},
    {"name": "Expensive", "below": None, "color": "#ef4444"},
]

# Price slot granularity
SLOT_MINUTES = 15
SLOTS_PER_HOUR = 60 // SLOT_MINUTES  # 4

# Minimum 15-min slots required to consider tomorrow's data complete.
# A normal day has 96 slots; DST spring-forward gives 92 (23 h × 4) and
# fall-back gives 100 (25 h × 4). The threshold sits below the DST minimum
# so a partial fetch is still rejected.
MIN_TOMORROW_SLOTS = 88

# ENTSO-E API
ENTSOE_BASE_URL = "https://web-api.tp.entsoe.eu/api"
ENTSOE_DOCUMENT_TYPE = "A44"
ENTSOE_XML_NS = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"

# Lovelace card
LOVELACE_CARD_URL = f"/{DOMAIN}/{DOMAIN}-card.js"

# Bidding zone EIC codes — display label -> EIC
PRICE_AREAS: dict[str, str] = {
    "FI - Finland": "10YFI-1--------U",
    "SE1 - Luleå": "10Y1001A1001A44P",
    "SE2 - Sundsvall": "10Y1001A1001A45N",
    "SE3 - Stockholm": "10Y1001A1001A46L",
    "SE4 - Malmö": "10Y1001A1001A47J",
    "NO1 - Oslo": "10YNO-1--------2",
    "NO2 - Kristiansand": "10YNO-2--------T",
    "NO3 - Trondheim": "10YNO-3--------J",
    "NO4 - Tromsø": "10YNO-4--------9",
    "NO5 - Bergen": "10Y1001A1001A48H",
    "DK1 - West Denmark": "10YDK-1--------W",
    "DK2 - East Denmark": "10YDK-2--------M",
    "EE - Estonia": "10Y1001A1001A39I",
    "LV - Latvia": "10YLV-1001A00074",
    "LT - Lithuania": "10YLT-1001A0008Q",
    "DE-LU - Germany/Luxembourg": "10Y1001A1001A82H",
    "FR - France": "10YFR-RTE------C",
    "NL - Netherlands": "10YNL----------L",
    "BE - Belgium": "10YBE----------2",
    "AT - Austria": "10YAT-APG------L",
    "PL - Poland": "10YPL-AREA-----S",
    "CZ - Czech Republic": "10YCZ-CEPS-----N",
    "SK - Slovakia": "10YSK-SEPS-----K",
    "HU - Hungary": "10YHU-MAVIR----U",
    "SI - Slovenia": "10YSI-ELES-----O",
    "HR - Croatia": "10YHR-HEP------M",
    "RO - Romania": "10YRO-TEL------P",
    "BG - Bulgaria": "10YCA-BULGARIA-R",
    "RS - Serbia": "10YCS-SERBIATSOV",
    "PT - Portugal": "10YPT-REN------W",
    "ES - Spain": "10YES-REE------0",
    "IT-North": "10Y1001A1001A73I",
    "GB - Great Britain": "10YGB----------A",
    "CH - Switzerland": "10YCH-SWISSGRIDZ",
    "GR - Greece": "10YGR-HTSO-----Y",
}

import requests
import json

with open("config.json", "r") as keys_fh:
    configuration_data = json.load(keys_fh)

def pull_new_data():
    for data_provider, provider_config in configuration_data["data_providers"].items():
        api_url = provider_config["api"]
        auth_replacements = provider_config["authentication"]

        full_api_url = api_url.format(**auth_replacements)

        print(data_provider, full_api_url)

        response = requests.get(full_api_url)

        with open(f"{data_provider}.json", "w") as data_fh:
            json.dump(response.json(), data_fh, ensure_ascii=False, indent=2)

def clean_ocpi_data(data):
    data.pop("timestamp", None)

    for station in data["data"]:
        station.pop("last_updated", None)

        station["operator"].pop("logo", None)

        for evse in station["evses"]:
            evse.pop("activation_date", None)
            evse.pop("last_updated", None)
            evse.pop("status", None)

            for connector in evse["connectors"]:
                connector.pop("last_updated", None)

    return data

def clean_electrify_america_data(data):
    for station in data:
        del station["status"]

        if "party_id" not in station:
            station["party_id"] = "ELA"

        if "country" not in station:
            station["country"] = "USA"

        if "operator" not in station:
            station["operator"] = {
                "name": "Electrify America",
                "website": "https://www.electrifyamerica.com/",
            }

        if "postalCode" in station:
            station["postal_code"] = station["postalCode"]
            del station["postalCode"]

        if "evses" not in station:
            station["evses"] = []

        for evse in station["evses"]:
            if "uid" not in evse:
                evse["uid"] = evse["id"]
                del evse["id"]

            if "evse_id" not in evse:
                evse["evse_id"] = evse["uid"]

            for connector in evse["connectors"]:
                if "voltage" in connector:
                    connector["max_voltage"] = connector["voltage"]
                    del connector["voltage"]

                if "amperage" in connector:
                    connector["max_amperage"] = connector["amperage"]
                    del connector["amperage"]

                if "format" not in connector:
                    connector["format"] = "CABLE"

    data = {
        "data": data,
    }
    data = clean_ocpi_data(data)

    return data

def clean_nrel_data(data):
    CLEAN_PREFIXES = [
        "bd_",
        "cng_",
        "e85_",
        "hy_",
        "lng_",
        "lpg_",
        "ng_",
        "rd_",
    ]

    del data["station_counts"]
    del data["total_results"]

    for station in data["fuel_stations"]:
        for field_name in list(station.keys()):
            to_remove = False

            for prefix in CLEAN_PREFIXES:
                if field_name.startswith(prefix):
                    to_remove = True

            if field_name.endswith("_fr"):
                to_remove = True

            if to_remove:
                del station[field_name]

        del station["date_last_confirmed"]
        del station["updated_at"]

    return data

def clean_ocm_data(data):
    for station in data:
        del station["DateCreated"]
        del station["DateLastVerified"]
        del station["DateLastStatusUpdate"]
        del station["IsRecentlyVerified"]

        del station["SubmissionStatus"]["ID"]

        if "AddressInfo" in station:
            del station["AddressInfo"]["Country"]["ID"]

        if "DateLastConfirmed" in station:
            del station["DateLastConfirmed"]

        if "DataProvider" in station:
            del station["DataProvider"]["ID"]
            del station["DataProvider"]["DataProviderStatusType"]
            del station["DataProvider"]["IsRestrictedEdit"]

            if "DateLastImported" in station["DataProvider"]:
                del station["DataProvider"]["DateLastImported"]

        if "OperatorInfo" in station:
            del station["OperatorInfo"]["ID"]
            if "IsRestrictedEdit" in station["OperatorInfo"]:
                del station["OperatorInfo"]["IsRestrictedEdit"]

        if "StatusType" in station:
            del station["StatusType"]["ID"]
            del station["StatusType"]["IsUserSelectable"]

        if "UsageType" in station:
            del station["UsageType"]["ID"]

        for connection in station["Connections"]:
            if "ConnectionType" in connection:
                del connection["ConnectionType"]["ID"]

            if "CurrentType" in connection:
                del connection["CurrentType"]["ID"]

            if "Level" in connection:
                del connection["Level"]["ID"]
                del connection["Level"]["Comments"]

            if "StatusType" in connection:
                del connection["StatusType"]["ID"]
                del connection["StatusType"]["IsUserSelectable"]

    return data

def clean_osm_data(data):
    del data["generator"]
    del data["version"]

    del data["osm3s"]["timestamp_osm_base"]
    del data["osm3s"]["timestamp_areas_base"]

    return data

def clean_supercharge_data(data):
    for station in data:
        del station["counted"]
        del station["statusDays"]
        del station["urlDiscuss"]

    data = sorted(data, key=lambda s: s["id"])

    return data

CLEANERS = {
    "electricera": clean_ocpi_data,
    "electrifyamerica": clean_electrify_america_data,
    "nrel": clean_nrel_data,
    "ocm": clean_ocm_data,
    "osm": clean_osm_data,
    "supercharge": clean_supercharge_data,
}

def fix_electricera_data(data, fixes):
    return data

def fix_electrify_america_data(data, fixes):
    return data

def fix_nrel_data(data, fixes):
    fix_map = {}

    for fix in fixes:
        fix_map[fix["id"]] = fix

    for station in data["fuel_stations"]:
        if station["id"] in fix_map:
            station.update(fix_map[station["id"]])

    return data

def fix_ocm_data(data, fixes):
    fix_map = {}

    for fix in fixes:
        fix_map[fix["ID"]] = fix

    for station in data:
        if station["ID"] not in fix_map:
            continue

        station_fixes = fix_map[station["ID"]]

        if "AddressInfo" in station_fixes:
            station["AddressInfo"].update(station_fixes["AddressInfo"])

            del station_fixes["AddressInfo"]

        station.update(station_fixes)

    return data

def fix_osm_data(data, fixes):
    return data

def fix_supercharge_data(data, fixes):
    fix_map = {}

    for fix in fixes:
        fix_map[fix["id"]] = fix

    for station in data:
        if station["id"] not in fix_map:
            continue

        station_fixes = fix_map[station["id"]]

        if "address" in station_fixes:
            station["address"].update(station_fixes["address"])

            del station_fixes["address"]

    return data

FIXERS = {
    "electricera": fix_electricera_data,
    "electrifyamerica": fix_electrify_america_data,
    "nrel": fix_nrel_data,
    "ocm": fix_ocm_data,
    "osm": fix_osm_data,
    "supercharge": fix_supercharge_data,
}

def clean_new_data():
    for data_provider, provider_config in configuration_data["data_providers"].items():
        with open(f"{data_provider}.json", "r") as data_fh:
            provider_data = json.load(data_fh)

        cleaned_data = CLEANERS[data_provider](provider_data)

        with open(f"{data_provider}-clean.json", "w") as data_fh:
            json.dump(cleaned_data, data_fh, ensure_ascii=False, indent=2)

def clean_existing_data():
    for data_provider in ["electrifyamerica"]:
        with open(f"{data_provider}-clean.json", "r") as data_fh:
            provider_data = json.load(data_fh)

        cleaned_data = CLEANERS[data_provider](provider_data)

        with open(f"{data_provider}-clean.json", "w") as data_fh:
            json.dump(cleaned_data, data_fh, ensure_ascii=False, indent=2)

def apply_fixes_for_data():
    for data_provider, provider_config in configuration_data["data_providers"].items():
        with open(f"{data_provider}-clean.json", "r") as data_fh:
            provider_data = json.load(data_fh)

        with open(f"{data_provider}-fixes.json", "r") as fixes_fh:
            fixes_data = json.load(fixes_fh)

        cleaned_data = FIXERS[data_provider](provider_data, fixes_data)

        with open(f"{data_provider}-clean.json", "w") as data_fh:
            json.dump(cleaned_data, data_fh, ensure_ascii=False, indent=2)

def detect_diffs_electrify_america(data: list[dict], extras) -> list[str]:
    extras_dict = {}

    for extra in extras:
        extras_dict[extra["id"]] = extra

    differing_ids = []

    for station in data:
        if station["state"] != "Massachusetts":
            continue

        extra = extras_dict.get(station["id"], {})

        if not extra:
            differing_ids.append(station["id"])
            continue

        attrs = ["siteId", "name", "address", "city", "postalCode", "state", "type"]

        for attr in attrs:
            if station[attr] != extra[attr]:
                differing_ids.append(station["id"])
                break

    return differing_ids

def retrieve_extras_electrify_america(config: dict, different_ids: list[str]) -> list[dict]:
    extras = []

    for id in different_ids:
        extras_url = config["extras_api"].format(id=id)

        response = requests.get(extras_url)

        extras.append(response.json())

    return extras

def retrieve_extras():
    with open("electrifyamerica.json", "r") as data_fh:
        provider_data = json.load(data_fh)

    with open("electrifyamerica-extras.json", "r") as extras_fh:
        provider_extras: list[dict] = json.load(extras_fh)

    different_ids = detect_diffs_electrify_america(provider_data, provider_extras)

    new_extras = retrieve_extras_electrify_america(configuration_data["data_providers"]["electrifyamerica"], different_ids)

    for extra in new_extras:
        existing_extra = False

        for old_extra in provider_extras:
            if extra["id"] != old_extra["id"]:
                continue

            old_extra.update(extra)
            existing_extra = True

            break

        if existing_extra:
            break

        provider_extras.append(extra)

    with open("electrifyamerica-extras.json", "w") as extras_fh:
        json.dump(provider_extras, extras_fh, ensure_ascii=False, indent=2)

def combine_data_with_extra():
    with open("electrifyamerica.json", "r") as data_fh:
        provider_data = json.load(data_fh)

    with open("electrifyamerica-extras.json", "r") as extras_fh:
        provider_extras: list[dict] = json.load(extras_fh)

    for extra in provider_extras:
        for station in provider_data:
            if station["id"] != extra["id"]:
                continue

            station.update(extra)

        with open(f"electrifyamerica-clean.json", "w") as data_fh:
            json.dump(provider_data, data_fh, ensure_ascii=False, indent=2)

pull_new_data()
clean_new_data()
apply_fixes_for_data()
retrieve_extras()
combine_data_with_extra()
clean_existing_data()

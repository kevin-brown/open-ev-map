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

    return data

CLEANERS = {
    "nrel": clean_nrel_data,
    "ocm": clean_ocm_data,
    "osm": clean_osm_data,
    "supercharge": clean_supercharge_data,
}

def clean_new_data():
    for data_provider, provider_config in configuration_data["data_providers"].items():
        with open(f"{data_provider}.json", "r") as data_fh:
            provider_data = json.load(data_fh)
        
        cleaned_data = CLEANERS[data_provider](provider_data)

        with open(f"{data_provider}-clean.json", "w") as data_fh:
            json.dump(cleaned_data, data_fh, ensure_ascii=False, indent=2)

# pull_new_data()
clean_new_data()

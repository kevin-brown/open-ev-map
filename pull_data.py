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
    return data

def clean_osm_data(data):
    return data

def clean_supercharge_data(data):
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

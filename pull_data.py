import requests
import json

with open("config.json", "r") as keys_fh:
    configuration_data = json.load(keys_fh)

for data_provider, provider_config in configuration_data["data_providers"].items():
    api_url = provider_config["api"]
    auth_replacements = provider_config["authentication"]

    full_api_url = api_url.format(**auth_replacements)

    print(data_provider, full_api_url)

    response = requests.get(full_api_url)

    with open(f"{data_provider}.json", "w") as data_fh:
        json.dump(response.json(), data_fh, ensure_ascii=False, indent=2)

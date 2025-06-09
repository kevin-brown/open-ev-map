from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, ReferenceFeature, SourceFeature, StationFeature

from scrapy.utils.project import get_project_settings
import scrapy


class RedeSpider(scrapy.Spider):
    name = "rede"

    CONNECTOR_TYPE_TO_PLUG_TYPE = {
        "J1772": "J1772_CABLE",
        "CCS": "J1772_COMBO",
        "CCS A": "J1772_COMBO",
        "CCS B": "J1772_COMBO",
        "CHADEMO": "CHADEMO",
        "NACS": "NACS",
    }

    def start_requests(self):
        settings = get_project_settings()
        auth_headers = {
            "Authorization": f"Bearer {settings.get('RED_E_ACCESS_TOKEN')}",
        }

        yield scrapy.http.FormRequest(
            url="https://pay.rede.network/laravel/index.php/api/search-site",
            formdata={
                "latitude": "37.4219983",
                "longitude": "-122.084",
            },
            headers=auth_headers,
            meta={
                "auth": auth_headers,
            },
            callback=self.parse_sites,
        )

    def parse_sites(self, response):
        stations = response.json()["data"]

        for station in stations:
            if station["state"] != "MA":
                continue

            for charging_station in station["charger_stations"]:
                connector_status = [connector["status"] for connector in charging_station["connectors"]]

                if all(status == "UNAVAILABLE" for status in connector_status):
                    continue

                yield scrapy.http.FormRequest(
                    url="https://pay.rede.network/laravel/index.php/api/get-charging-station-by-id",
                    formdata={
                        "qr_code": charging_station["qr_code"],
                    },
                    headers=response.meta["auth"],
                    meta={
                        "auth": response.meta["auth"],
                    },
                    callback=self.parse_charging_station,
                )

    def parse_charging_station(self, response):
        charging_station = response.json()["data"]

        if not charging_station:
            return

        site = charging_station["site"]

        address = AddressFeature(
            street_address=site["address"],
            city=site["city"],
            state=site["state"],
            zip_code=site["postal_code"],
        )

        coordinates = LocationFeature(
            latitude=site["latitude"],
            longitude=site["longitude"],
        )

        evses = []

        for connector in charging_station["connectors"]:
            evse_id = str(charging_station["id"])

            if len(charging_station["connectors"]) > 1:
                evse_id += "*" + str(connector["sequence_number"])

            evses.append(
                EvseFeature(
                    network_id=evse_id,
                    plugs=[
                        ChargingPortFeature(
                            plug=self.CONNECTOR_TYPE_TO_PLUG_TYPE[connector["type"]],
                            power=PowerFeature(
                                output=int(connector["connector_output"] * 1000),
                                voltage=connector["voltage"],
                            ),
                        ),
                    ],
                )
            )

        charging_point = ChargingPointFeature(
            name=charging_station["name"],
            location=coordinates,
            network_id=charging_station["id"],
            evses=evses,
        )

        yield StationFeature(
            name=site["name"],
            network="RED_E",
            network_id=site["id"],
            charging_points=[charging_point],
            address=address,
            location=coordinates,
            source=SourceFeature(
                system="RED_E",
                quality="ORIGINAL",
            ),
        )

from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

from scrapy.utils.project import get_project_settings
import scrapy

import json


class AmpedUpSpider(scrapy.Spider):
    name = "ampedup"

    CONNECTOR_TO_PLUG_TYPE = {
        "J1772": "J1772_CABLE",
    }

    def start_requests(self):
        settings = get_project_settings()
        auth_token = settings.get("AMPED_UP_ACCESS_TOKEN")

        yield scrapy.http.JsonRequest(
            url="https://ampedup-chargingstationapi-prod.azurewebsites.net/api/SearchChargersByLocation?code=voPIjjhin47lGzXcji/9ykWuMoCUVat2/cjh2gP8PkZHenG5mlRwxQ==",
            data={
                "Distance": 1000000,
                "location": {
                    "type": "Point",
                    "coordinates": [
                        42.13,
                        -71.76,
                    ],
                },
                "userLocation": {
                    "type": "Point",
                    "coordinates": [
                        42.13,
                        -71.76,
                    ],
                },
            },
            headers={
                "Authorization": f"Bearer {auth_token}",
            },
            meta={
                "authorization": f"Bearer {auth_token}",
            },
            callback=self.parse_locations,
        )
    
    def parse_locations(self, response):
        locations = response.json()

        for location in locations:
            address_parts = location["chargerAddress"].split()
            state = address_parts[-2]

            if state != "MA":
                continue

            yield scrapy.http.JsonRequest(
                url="https://ampedup-chargingstationapi-prod.azurewebsites.net/api/GetChargingStation?code=liVJc0LIRQ4YsSqDrdl9YOagw0VVUkkdjfUrkETQzY84f8jkq4kuJQ==",
                data={
                    "iotHubDeviceId": location["iotHubDeviceId"],
                    "location": location["location"],
                    "bypassDirection": True,
                    "coupon": ""
                },
                headers={
                    "Authorization": response.meta["authorization"],
                },
                callback=self.parse_location,
            )

    def parse_location(self, response):
        location = response.json()

        print(location)

        address_city, state_zip = location["chargerAddress"].split(", ")
        state, zip_code = state_zip.rsplit(" ", 1)
        city = address_city[len(location["chargerAddress1"].strip()) + 1:]

        address = AddressFeature(
            street_address=location["chargerAddress1"].strip(),
            city=city,
            state=state,
            zip_code=zip_code,
        )

        coordinates = LocationFeature(
            latitude=location["location"]["coordinates"][0],
            longitude=location["location"]["coordinates"][1],
        )

        evses = []

        for evse in location["evses"]:
            for connector in evse["connectors"]:
                plug = ChargingPortFeature(
                    plug=self.CONNECTOR_TO_PLUG_TYPE[connector["connectorType"]],
                    power=PowerFeature(
                        voltage=location["voltage"],
                        amperage=location["maxCurrent"],
                        output=int(location["power"] * 1000),
                    )
                )

                evses.append(
                    EvseFeature(
                        network_id=connector["csoCircuitId"],
                        plugs=[plug],
                    )
                )

        charging_point = ChargingPointFeature(
            name=location["chargerName"],
            network_id=location["iotHubDeviceId"],
            location=coordinates,
            evses=evses,
            hardware=HardwareFeature(
                manufacturer=location["chargePointVendor"],
                model=location["chargePointModel"],
            ),
        )

        yield StationFeature(
            name=location["locationName"],
            network="AMPED_UP",
            network_id=location["csoLocationId"],
            address=address,
            location=coordinates,
            charging_points=[charging_point],
            source=SourceFeature(
                system="AMPED_UP",
                quality="ORIGINAL",
            ),
        )

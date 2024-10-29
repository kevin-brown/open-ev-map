from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, StationFeature

import scrapy
import urllib.parse


class EvconnectSpider(scrapy.Spider):
    name = "evconnect"

    handle_httpstatus_list = [200, 400]

    CONNECTOR_TO_PLUG_MAP = {
        "SAE": "J1772_CABLE",
        "CCS": "J1772_COMBO",
        "CHADEMO": "CHADEMO",
    }

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://api.evconnect.com/mobile/rest/v6/networks/ev-connect/auth/guest",
            method="POST",
        )

    def parse(self, response):
        auth_data = response.json()

        yield scrapy.http.JsonRequest(
            url="https://api.evconnect.com/mobile/rest/v6/networks/ev-connect/locations-geo-search?" + urllib.parse.urlencode({
                "longitude": -71.76,
                "latitude": 42.13,
                "distance": 150,
                "metric": "MILES",
                "freeOnly": "false",
                "includeRoaming": "false",
                "evoucherDiscountOnly": "false",
                "availableOnly": "false",
            }),
            headers={
                "evc-api-token": auth_data["accessToken"],
            },
            method="GET",
            meta={
                "auth": auth_data,
            },
            callback=self.parse_locations,
        )

    def parse_locations(self, response):
        locations = response.json()

        print(locations)

        location_identifiers = []

        for location in locations:
            location_identifiers.append({
                "locationId": location["e"],
                "operatorId": location["o"],
            })

        yield scrapy.http.JsonRequest(
            url="https://api.evconnect.com/mobile/rest/v6/networks/ev-connect/locations",
            data={
                "locationIdentifiers": location_identifiers,
                "powerLevels": [],
                "availableOnly": False,
                "evoucherDiscountOnly": False,
                "freeOnly": False,
            },
            headers={
                "evc-api-token": response.meta["auth"]["accessToken"],
            },
            meta={
                "auth": response.meta["auth"],
            },
            method="POST",
            callback=self.parse_locations_verbose,
        )

    def parse_locations_verbose(self, response):
        locations = response.json()

        for location in locations:
            for port in location["ports"]:
                yield scrapy.http.JsonRequest(
                    url=f"https://api.evconnect.com/mobile/rest/v6/users/current/station-ports?qrCode={port["qrCode"]}",
                    headers={
                        "evc-api-token": response.meta["auth"]["accessToken"],
                    },
                    meta={
                        "auth": response.meta["auth"],
                    },
                    method="GET",
                    callback=self.parse_ports,
                )

            return

    def parse_ports(self, response):
        location = response.json()

        coordinates = LocationFeature(**location["geoLocation"])

        plugs = []

        for connector in location["connectors"]:
            plugs.append(ChargingPortFeature(
                plug=self.CONNECTOR_TO_PLUG_MAP[connector["connectorType"]],
            ))

        charging_point = ChargingPointFeature(
            name=location["qrCode"],
            evses=[EvseFeature(
                plugs=plugs,
            )]
        )

        yield StationFeature(
            name=location["locationName"],
            network="EV_CONNECT",
            network_id=location["locationId"],
            location=coordinates,
            charging_points=[charging_point],
        )

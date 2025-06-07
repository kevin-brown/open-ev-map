from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature
from scrapers.utils import MAPPER_STATE_ABBR_LONG_TO_SHORT

import scrapy

import base64
import json
import uuid


class NoodoeSpider(scrapy.Spider):
    name = "noodoe"

    def start_requests(self):
        client_info = {
            "app": "noodoe",
            "dm": "android-Google sdk_gphone64_x86_64",
            "dn": str(uuid.uuid4()),
            "vn": "2.34.3 (23403001)",
            "ts": 1732994697103,
            "tz": -300,
            "cn": "US",
            "lang": "en",
            "os": "Android SDK: 34 (14)",
            "alg": "HS256"
        }

        client_info_token = base64.b64encode(json.dumps(client_info).encode("ascii")).decode("ascii")

        query = """
        query RegionLocationsQuery($filter: LocationFilter, $input: RegionSearchInput!) {
            mapQuery {
                regionLocations(filter: $filter, input: $input) {
                    id
                    name
                    address
                    coordinate {
                        longitude
                        latitude
                    }
                    roamingPartner {
                        partyId
                        countryCode
                        name
                    }
                    stations {
                        id
                        name
                        kw
                        network {
                            id
                            name
                        }
                        outlets {
                            id
                            connectorId
                            description
                            power
                        }
                    }
                }
            }
        }
        """

        yield scrapy.http.JsonRequest(
            url="https://napp-prod.noodoe.com/graphql",
            data={
                "operationName": "RegionLocationsQuery",
                "variables": {
                    "filter": {
                        "networks": [],
                        "outlets": [],
                        "connectors": [],
                        "chargingAvailableOnly": False,
                        "autochargeOnly": False,
                        "accessTypes": [
                            "PUBLIC",
                            "RESTRICTED",
                        ],
                        "badges": {
                            "isFilterAllUserBadges": False,
                            "values": [],
                        },
                        "powerLevels": [],
                        "showFreeOnly": False,
                    },
                    "input": {
                        "latitude": 41.0,
                        "longitude": -69.6,
                        "spanLat": 6,
                        "spanLon": 4,
                        "size": 500,
                    },
                },
                "query": query,
            },
            headers={
                "N-Client-Info": client_info_token,
            },
            meta={
                "client_info": client_info_token,
            },
            callback=self.parse_locations,
        )

    def parse_locations(self, response):
        locations = response.json()["data"]["mapQuery"]["regionLocations"]

        for location in locations:
            address_info = self._parse_address(location["address"])

            if address_info["state"] != "MA":
                continue

            roaming_partner_map = {
                "ABM": "ABM",
            }

            connector_id_map = {
                2: "J1772_CABLE",
            }

            coordinates = LocationFeature(
                latitude=location["coordinate"]["latitude"],
                longitude=location["coordinate"]["longitude"],
            )

            address = AddressFeature(
                **address_info,
            )

            charging_points = []

            for station in location["stations"]:
                evses = []

                for outlet in station["outlets"]:
                    evses.append(
                        EvseFeature(
                            plugs=[
                                ChargingPortFeature(
                                    plug=connector_id_map[outlet["connectorId"]],
                                    power=PowerFeature(
                                        output=int(station["kw"] * 1000),
                                    ),
                                ),
                            ],
                        )
                    )

                charging_points.append(
                    ChargingPointFeature(
                        name=station["name"],
                        network_id=station["id"],
                        evses=evses,
                    ),
                )

            yield StationFeature(
                name=location["name"],
                network=roaming_partner_map[location["roamingPartner"]["partyId"]],
                network_id=location["id"],
                location=coordinates,
                address=address,
                charging_points=charging_points,
                source=SourceFeature(
                    system="NOODOE",
                    quality="ORIGINAL",
                ),
            )

    def _parse_address(self, address):
        street_address, city, state_zip, _ = address.split(", ")

        full_state, zip_code = state_zip.rsplit(" ", 1)

        if len(full_state) > 2:
            state = MAPPER_STATE_ABBR_LONG_TO_SHORT[full_state]
        else:
            state = full_state

        return {
            "street_address": street_address,
            "city": city,
            "state": state,
            "zip_code": zip_code,
        }

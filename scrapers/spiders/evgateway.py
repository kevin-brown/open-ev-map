from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

import scrapy


class EvgatewaySpider(scrapy.Spider):
    name = "evgateway"
    org_id = 1

    STANDARD_TO_PLUG_TYPE_MAP = {
        "IEC_62196_T1": "J1772_CABLE",
        "IEC_62196_T1_COMBO": "J1772_COMBO",
        "CHADEMO": "CHADEMO",
    }

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url=f"https://mobileapi.evgateway.com/api/v3/info/sites?orgId={self.org_id}&lat=42.13&lng=-71.76&radius=145",
        )

    def parse(self, response):
        locations = response.json()["data"]

        for location in locations:
            yield scrapy.http.JsonRequest(
                url="https://mobileapi.evgateway.com/api/v3/info/siteDetails",
                data={
                    "capacity": [],
                    "chargerType": [],
                    "connectorType": [],
                    "deviceToken": "test-token",
                    "filter": False,
                    "lat": location["latitude"],
                    "lng": location["longitude"],
                    "network": [],
                    "networkString": [],
                    "orgId": self.org_id,
                    "price": {
                        "free": False,
                    },
                    "radius": 50,
                    "siteId": location["id"],
                    "status": [],
                    "uuid": "",
                },
                callback=self.parse_site,
            )

    def parse_site(self, response):
        location = response.json()["data"]

        coordinates = LocationFeature(
            latitude=location["latitude"],
            longitude=location["longitude"],
        )

        address_parts = location["address"].split()
        address = AddressFeature(
            state=address_parts[-3],
            zip_code=address_parts[-1],
        )

        if address_parts[-3] != "MA":
            return

        charging_points = []

        for station in location["stations"]:
            evses = []

            for port in station["ports"]:
                evses.append(
                    EvseFeature(
                        network_id=port["id"],
                        plugs=[
                            ChargingPortFeature(
                                plug=self.STANDARD_TO_PLUG_TYPE_MAP[port["connectorType"]],
                                power=PowerFeature(
                                    output=int(port["capacity"] * 1000),
                                )
                            )
                        ]
                    )
                )

            charging_points.append(
                ChargingPointFeature(
                    name=station["name"],
                    network_id=station["id"],
                    evses=evses,
                )
            )

        yield StationFeature(
            name=location["name"],
            network="EV_GATEWAY",
            network_id=location["id"],
            location=coordinates,
            address=address,
            charging_points=charging_points,
            source=SourceFeature(
                quality="ORIGINAL",
                system="EV_GATEWAY",
            ),
        )

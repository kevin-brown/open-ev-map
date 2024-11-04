from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

import scrapy


class ShellRechargeSpider(scrapy.Spider):
    name = "shellrecharge"

    PLUG_TYPE_TO_PLUG_MAP = {
        "SAEJ1772": "J1772_CABLE",
        "CCS": "J1772_COMBO",
        "CHAdeMO": "CHADEMO",
    }

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://sky.shellrecharge.com/greenlots/coreapi/v4/sites/search",
            data={
                "latitude": 42.13,
                "longitude": -71.76,
                "limit": 100000,
                "offset": 0,
                "status": [],
                "connectors": [],
                "searchKey": "",
                "mappedCpos": [
                    "GRL",
                ]
            },
            method="POST",
        )

    def parse(self, response):
        stations = response.json()["data"]

        for station in stations:
            location = LocationFeature(
                latitude=station["latitude"],
                longitude=station["longitude"],
            )
            address = AddressFeature(
                street_address=station["address"],
                city=station["city"],
                state=station["state"],
                zip_code=station["zipCode"],
            )

            charging_points = []

            for station_evse in station["evses"]:
                plugs = []

                for connector in station_evse["ports"]:
                    power = PowerFeature(
                        amperage=connector["current"],
                        voltage=connector["voltage"],
                        output=connector["maxElectricPower"],
                    )

                    plug = ChargingPortFeature(
                        plug=self.PLUG_TYPE_TO_PLUG_MAP[connector["plugType"]],

                        power=power,
                    )
                    plugs.append(plug)

                evse = EvseFeature(
                    plugs=plugs,
                )

                hardware = HardwareFeature(
                    manufacturer=station_evse["evseManufacturerName"],
                    model=station_evse["evseModelName"],
                )

                charging_point = ChargingPointFeature(
                    name=station_evse["evseDisplayId"],
                    network_id=station_evse["evseEmaid"],
                    location=location,
                    evses=[evse],
                    hardware=hardware,
                )
                charging_points.append(charging_point)

            yield StationFeature(
                name=station["name"],
                network="SHELL_RECHARGE",
                network_id=station["locationId"],
                location=location,
                address=address,
                charging_points=charging_points,
                source=SourceFeature(
                    quality="ORIGINAL",
                    system="SHELL_RECHARGE_GREENLOTS",
                ),
            )

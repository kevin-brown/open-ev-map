from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, StationFeature
from scrapers.spiders.ocpi import OcpiSpider

import scrapy


class ShellRechargeSpider(OcpiSpider):
    name = "shellrecharge"
    network="SHELL_RECHARGE"

    PLUG_TYPE_TO_STANDARD_MAP = {
        "SAEJ1772": "IEC_62196_T1",
        "CCS": "IEC_62196_T1_COMBO",
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
            station["coordinates"] = {
                "latitude": station["latitude"],
                "longitude": station["longitude"],
            }

            station["postal_code"] = station["zipCode"]
            station["id"] = station["locationId"]

            for evse in station["evses"]:
                evse["connectors"] = evse["ports"]
                evse["physical_reference"] = evse["evseDisplayId"]
                evse["evse_id"] = evse["evseEmaid"]

                evse["manufacturer"] = evse["evseManufacturerName"]
                evse["model"] = evse["evseModelName"]

                for connector in evse["connectors"]:
                    connector["standard"] = self.PLUG_TYPE_TO_STANDARD_MAP[connector["plugType"]]

                    connector["max_amperage"] = connector["current"]
                    connector["max_voltage"] = connector["voltage"]
                    connector["max_electric_power"] = connector["maxElectricPower"]

            yield from self.station_to_feature(station)

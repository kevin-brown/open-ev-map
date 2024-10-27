from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, LocationFeature, StationFeature
from scrapers.spiders.ocpi import OcpiSpider

import scrapy


class ElectrifyAmericaSpider(OcpiSpider):
    name = "electrifyamerica"
    start_urls = ["https://api-prod.electrifyamerica.com/v2/locations"]
    network = "ELECTRIFY_AMERICA"

    STANDARD_TO_PLUG_TYPE_MAP = {
        "IEC_62196_T1": "J1772",
        "IEC_62196_T1_COMBO": "J1772_COMBO",
        "CHADEMO": "CHADEMO",
    }

    def parse(self, response):
        stations = response.json()

        for station in stations:
            if station["state"] != "Massachusetts":
                continue

            if station["type"] == "COMING_SOON":
                continue

            yield scrapy.http.JsonRequest(
                url=f"https://api-prod.electrifyamerica.com/v2/locations/{station["id"]}",
                method="GET",
                meta={
                    "summary": station,
                },
                callback=self.parse_station,
            )

    def parse_station(self, response):
        station = response.json()
        station["postal_code"] = station["postalCode"]

        for evse in station["evses"]:
            evse["evse_id"] = evse["id"]
            evse["physical_reference"] = evse["id"]

            evse["brand"] = "Electrify America"

            for connector in evse["connectors"]:
                connector["max_amperage"] = connector["amperage"]
                connector["max_voltage"] = connector["voltage"]

        yield from self.station_to_feature(station)

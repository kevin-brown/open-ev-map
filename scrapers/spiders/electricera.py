from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, LocationFeature, StationFeature
from scrapers.spiders.ocpi import OcpiSpider

import scrapy


class ElectricEraSpider(OcpiSpider):
    name = "electricera"
    start_urls = ["https://ocpi-http.app.electricera.tech/ocpi/2.2/locations"]
    network = "ELECTRIC_ERA"
    system = "ELECTRIC_ERA"

    def parse(self, response):
        stations = response.json()["data"]

        for station in stations:
            if station["state"] != "Massachusetts":
                continue

            if station["station_type"] == "COMING_SOON":
                continue

            yield from self.station_to_feature(station)

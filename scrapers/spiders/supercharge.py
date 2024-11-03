from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, LocationFeature, SourceFeature, StationFeature

import scrapy


class SuperchargeSpider(scrapy.Spider):
    name = "supercharge"
    start_urls = ["https://supercharge.info/service/supercharge/allSites"]

    PLUG_TYPE_TO_PLUG_MAP = {
        "ccs1": "J1772_COMBO",
        "nacs": "NACS",
        "tpc": "NACS",

        "multi": None,
    }

    def parse(self, response):
        stations = response.json()

        for station in stations:
            if station["status"] not in ["OPEN", "EXPANDING"]:
                continue

            station_address = station["address"]

            if station_address["countryId"] != 100:
                continue

            if station_address["state"] != "MA":
                continue

            address = AddressFeature(
                street_address=station_address["street"],
                city=station_address["city"],
                state=station_address["state"],
                zip_code=station_address["zip"],
            )

            location = LocationFeature(**station["gps"])

            yield StationFeature(
                name=station["name"],
                network="TESLA_SUPERCHARGER",
                network_id=station["locationId"],
                address=address,
                location=location,
                source=SourceFeature(
                    quality="CURATED",
                    system="SUPERCHARGE",
                ),
            )

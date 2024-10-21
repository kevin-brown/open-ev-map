from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, LocationFeature, StationFeature

import scrapy


class ElectrifyAmericaSpider(scrapy.Spider):
    name = "electrifyamerica"
    start_urls = ["https://api-prod.electrifyamerica.com/v2/locations"]

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

        location = LocationFeature(**station["coordinates"])
        address = AddressFeature(
            street_address=station["address"],
            city=station["city"],
            state=station["state"],
            zip_code=station["postalCode"],
        )

        charging_points = []

        for station_evse in station["evses"]:
            plugs = []

            for connector in station_evse["connectors"]:
                plug = ChargingPortFeature(
                    plug=self.STANDARD_TO_PLUG_TYPE_MAP[connector["standard"]],
                )
                plugs.append(plug)

            evse = EvseFeature(
                plugs=plugs,
            )

            charging_point = ChargingPointFeature(
                name=station_evse["id"],
                network_id=station_evse["id"],
                location=location,
                evses=[evse],
            )
            charging_points.append(charging_point)

        yield StationFeature(
            name=station["name"],
            network="ELECTRIFY_AMERICA",
            network_id=station["id"],
            location=location,
            address=address,
            charging_points=charging_points,
        )

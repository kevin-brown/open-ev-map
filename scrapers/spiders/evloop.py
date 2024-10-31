from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, StationFeature

import scrapy


class EvloopSpider(scrapy.Spider):
    name = "evloop"

    CHARGER_TYPE_TO_PLUG_MAP = {
        "J1772": "J1772_CABLE",
        "CCS Type 1": "J1772_COMBO",
        "CCS Type 2": None,
        "CHAdeMO": "CHADEMO",
    }

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://api.evloop.io/v1.0/residences?page=0&limit=200&locationLatitude=42.13&locationLongitude=-71.76",
        )

    def parse(self, response):
        sites = response.json()["rows"]

        for site in sites:
            if site["state"]["title"] != "Massachusetts":
                continue

            location = LocationFeature(
                latitude=site["latitude"],
                longitude=site["longitude"],
            )

            city = site["city"]["title"]
            street_address = site["address"].rsplit(city, 1)[0]

            address = AddressFeature(
                street_address=street_address,
                city=city,
                state=site["state"]["title"],
                zip_code=site["zipCode"],
            )

            charging_points = []

            for charger in site["chargers"]:
                evses = []

                if len(charger["chargerTypes"]) == 1:
                    for _ in range(charger["allConnectorsNumber"]):
                        evses.append(EvseFeature(
                            plugs=[ChargingPortFeature(
                                plug=self.CHARGER_TYPE_TO_PLUG_MAP[charger["chargerTypes"][0]],
                            )]
                        ))
                elif charger["allConnectorsNumber"] == len(charger["chargerTypes"]):
                    ports = []

                    for plug_type in charger["chargerTypes"]:
                        ports.append(ChargingPortFeature(
                            plug=self.CHARGER_TYPE_TO_PLUG_MAP[plug_type],
                        ))

                    evses.append(EvseFeature(
                        plugs=ports,
                    ))

                charging_points.append(ChargingPointFeature(
                    network_id=charger["id"],
                    evses=evses,
                ))

            yield StationFeature(
                name=site["title"],
                network="LOOP",
                network_id=site["id"],
                location=location,
                address=address,
                charging_points=charging_points,
            )

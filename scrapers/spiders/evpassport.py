from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

from uszipcode.state_abbr import MAPPER_STATE_ABBR_LONG_TO_SHORT
import scrapy


class EvpassportSpider(scrapy.Spider):
    name = "evpassport"

    CONNECTOR_TO_PLUG_MAP = {
        "J1772": "J1772_CABLE",
        "CCS": "J1772_COMBO",
    }

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://emsp.evpassport.com/android/api/v1/locations?ne=43.0,-69.6&sw=41.0,-73.6",
        )

    def parse(self, response):
        locations = response.json()["content"]

        for location in locations:
            yield scrapy.http.JsonRequest(
                url=f"https://emsp.evpassport.com/android/api/v1/locations/{location["id"]}",
                callback=self.parse_location,
                meta={
                    "location": location,
                }
            )

    def parse_location(self, response):
        location = response.json()["content"]
        meta_location = response.meta["location"]

        if location["state"] != "Massachusetts":
            return

        coordinates = LocationFeature(
            latitude=meta_location["coordinates"]["lat"],
            longitude=meta_location["coordinates"]["lng"],
        )

        address = AddressFeature(
            street_address=location["address"],
            city=location["city"],
            state=MAPPER_STATE_ABBR_LONG_TO_SHORT[location["state"]],
            zip_code=location["postalCode"],
        )

        charging_points = []

        for charger in meta_location["chargers"]:
            evses = []

            for evse in charger["evses"]:
                power = PowerFeature(
                    output=int(evse["connector"]["maxElectricPower"]["value"] * 1000),
                )

                plug = ChargingPortFeature(
                    plug=self.CONNECTOR_TO_PLUG_MAP[evse["connector"]["standard"]],
                    power=power,
                )

                evses.append(
                    EvseFeature(
                        network_id=evse["uid"],
                        plugs=[plug],
                    )
                )

            charging_points.append(
                ChargingPointFeature(
                    name=charger["physicalReference"],
                    evses=evses,
                )
            )

        yield StationFeature(
            name=location["name"],
            network="EV_PASSPORT",
            network_id=location["id"],
            location=coordinates,
            address=address,
            charging_points=charging_points,
            source=SourceFeature(
                quality="ORIGINAL",
                system="EV_PASSPORT",
            ),
        )

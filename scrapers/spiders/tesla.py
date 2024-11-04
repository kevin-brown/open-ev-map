from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

import scrapy
import shapely

import re
import string


class TeslaSpider(scrapy.Spider):
    name = "tesla"
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/130.0',
    }

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://www.tesla.com/cua-api/tesla-locations?translate=en_US&usetrt=true",
            callback=self.parse_locations,
        )

    def parse_locations(self, response):
        locations = response.json()

        MA_BOUNDARY = shapely.box(
            xmin=43.0,
            xmax=-69.6,
            ymin=41.0,
            ymax=-73.6,
        )

        for location in locations:
            if location["open_soon"] == "1":
                continue

            coordinates = shapely.Point(location["latitude"], location["longitude"])

            if not MA_BOUNDARY.contains(coordinates):
                continue

            charger_types = ["destination charger", "supercharger"]

            for charger_type in charger_types:
                if charger_type not in location["location_type"]:
                    continue

                yield scrapy.http.JsonRequest(
                    url=f"https://www.tesla.com/cua-api/tesla-location?translate=en_US&usetrt=true&id={location["location_id"]}",
                    callback=self.parse_location_response,
                )

    def parse_location_response(self, response):
        location = response.json()

        if location["country_code"] != "US":
            return

        if location["province_state"] != "MA":
            return

        if "destination charger" in location["location_type"]:
            yield from self.parse_destination_charger(location)

        if "supercharger" in location["location_type"] and "superchargerTitle" in location:
            yield from self.parse_supercharger(location)

    def parse_address(self, location, charger_address):
        return AddressFeature(
            street_address=charger_address["address_line_1"],
            city=charger_address["city"],
            state=location["province_state"],
            zip_code=charger_address["postal_code"],
        )

    def parse_location(self, location):
        return LocationFeature(
            latitude=location["latitude"],
            longitude=location["longitude"],
        )

    def parse_charging_point(self, charger_power, plug_types):
        plugs = []

        for plug in plug_types:
            plugs.append(
                ChargingPortFeature(
                    plug=plug,
                    power=PowerFeature(
                        output=charger_power * 1000,
                    ),
                )
            )

        hardware = HardwareFeature(
            manufacturer="TESLA",
            brand="TESLA",
        )

        if charger_power == 72:
            hardware["model"] = "Urban Charger"
        elif charger_power == 150:
            hardware["model"] = "V2 Charger"

        if charger_power > 50:
            hardware["brand"] = "TESLA_SUPERCHARGER"

        return ChargingPointFeature(
            evses=[
                EvseFeature(
                    plugs=plugs,
                )
            ],
            hardware=hardware,
        )

    def parse_destination_charger(self, location):
        charger_info = location["destChargers"]
        charger_count_matches = re.findall(r"(\d+) Connectors up to (\d+)kW", charger_info)

        charging_points = []

        charger_speeds = []

        if charger_count_matches:
            for match in charger_count_matches:
                charger_speeds.append([int(match[0]), int(match[1])])

        for charger_count, charger_power in charger_speeds:
            for _ in range(charger_count):
                charging_points.append(
                    self.parse_charging_point(charger_power, ["NACS"])
                )

        yield StationFeature(
            name=location["destinationChargerTitle"],
            network="TESLA_DESTINATION",
            network_id=location["location_id"],
            address=self.parse_address(location, location["destinationChargerAddress"]),
            location=self.parse_location(location),
            charging_points=charging_points,
            source=SourceFeature(
                quality="ORIGINAL",
                system="TESLA",
            ),
        )

    def parse_supercharger(self, location):
        charger_info = location["chargers"]
        charger_count_matches = re.findall(r"(\d+) Superchargers up to (\d+)kW(, Available 24/7)?", charger_info)

        has_ccs = "Other EVs with CCS compatibility" in charger_info

        charging_points = []

        charger_speeds = []

        if charger_count_matches:
            for match in charger_count_matches:
                charger_speeds.append([int(match[0]), int(match[1])])

        for charger_count, charger_power in charger_speeds:
            plugs = ["NACS"]
            if has_ccs:
                plugs.append("J1772_COMBO")
            for _ in range(charger_count):
                charging_points.append(
                    self.parse_charging_point(charger_power, plugs)
                )

        if len(charger_speeds) == 1:
            charger_count, charger_power = charger_speeds[0]
            for i in range(charger_count):
                if charger_power == 150:
                    letter = string.ascii_uppercase[(i % 2)]
                    number = (i // 2) + 1

                    charging_points[i]["name"] = f"{number}{letter}"
                elif charger_power == 250:
                    letter = string.ascii_uppercase[(i % 4)]
                    number = (i // 4) + 1

                    charging_points[i]["name"] = f"{number}{letter}"

        yield StationFeature(
            name=location["superchargerTitle"],
            network="TESLA_SUPERCHARGER",
            network_id=location["location_id"],
            address=self.parse_address(location, location["chargerAddress"]),
            location=self.parse_location(location),
            charging_points=charging_points,
            source=SourceFeature(
                quality="ORIGINAL",
                system="TESLA",
            ),
        )

from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, ReferenceFeature, SourceFeature, StationFeature

import scrapy

from collections import defaultdict
import string


class SuperchargeSpider(scrapy.Spider):
    name = "supercharge"
    start_urls = ["https://supercharge.info/service/supercharge/allSites"]

    PLUG_TYPE_TO_PLUG_MAP = {
        "ccs1": "J1772_COMBO",
        "nacs": "NACS",
        "tpc": "NACS",

        "multi": None,
    }

    STALL_TYPE_TO_MODEL_MAP = {
        "urban": "Urban Charger",
        "v2": "V2 Charger",
        "v3": "V3 Charger",
        "v4": "V4 Charger",
    }

    MAX_STALL_POWER = {
        "urban": 72,
        "v2": 150,
        "v3": 250,
        "v4": 250,
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

            references = []
            if "osmId" in station:
                references.append(
                    ReferenceFeature(
                        identifier=f"node:{station["osmId"]}",
                        system="OPEN_STREET_MAP",
                    )
                )

            street_address = station_address["street"]

            if ", " in street_address:
                street_address = street_address.split(", ")[-1]

            address = AddressFeature(
                street_address=street_address,
                city=station_address["city"],
                state=station_address["state"],
                zip_code=station_address["zip"],
            )

            location = LocationFeature(**station["gps"])

            stalls = station["stalls"].copy()
            stalls.pop("accessible", None)
            stalls.pop("trailerFriendly", None)

            plugs = station["plugs"].copy()

            for plug_type, plug_count in plugs.copy().items():
                if plug_count == 0:
                    plugs.pop(plug_type)
                elif plug_type == "multi":
                    plugs.pop(plug_type)

            stall_plugs = defaultdict(list)

            if len(plugs) == 1:
                plug_type = list(plugs.keys())[0]

                for stall_type in stalls.keys():
                    stall_plugs[stall_type].append(self.PLUG_TYPE_TO_PLUG_MAP[plug_type])
            else:
                for plug_type, plug_count in plugs.items():
                    for stall_type, stall_count in stalls.items():
                        if stall_count == plug_count:
                            stall_plugs[stall_type].append(self.PLUG_TYPE_TO_PLUG_MAP[plug_type])


            charging_points = []

            for stall_type, stall_count in stalls.items():
                for _ in range(stall_count):
                    plug_types = stall_plugs[stall_type]

                    max_power = min(self.MAX_STALL_POWER[stall_type], station["powerKilowatt"])

                    power = PowerFeature(
                        output=int(max_power * 1000),
                    )

                    if stall_type == "v2":
                        power["voltage"] = 410
                        power["amperage"] = 350
                    elif stall_type == "v3":
                        power["voltage"] = 500
                        power["amperage"] = 631
                    elif stall_type == "v4":
                        power["voltage"] = 1000
                        power["amperage"] = 615

                    plugs = []

                    for plug_type in plug_types:
                        plugs.append(
                            ChargingPortFeature(
                                plug=plug_type,
                                power=power,
                            )
                        )

                    hardware = HardwareFeature(
                        manufacturer="TESLA",
                        model=self.STALL_TYPE_TO_MODEL_MAP[stall_type],
                        brand="TESLA_SUPERCHARGER",
                    )

                    charging_points.append(
                        ChargingPointFeature(
                            evses=[
                                EvseFeature(
                                    plugs=plugs,
                                )
                            ],
                            hardware=hardware,
                        )
                    )

            if len(stalls) == 1 and "urban" not in stalls:
                stall_type = list(stalls.keys())[0]

                for i, charging_point in enumerate(charging_points):
                    if stall_type == "v2":
                        letter = string.ascii_uppercase[(i % 2)]
                        number = (i // 2) + 1

                        charging_point["name"] = f"{number}{letter}"
                    elif stall_type in ["v3", "v4"]:
                        letter = string.ascii_uppercase[(i % 4)]
                        number = (i // 4) + 1

                        charging_point["name"] = f"{number}{letter}"

            yield StationFeature(
                name=station["name"],
                network="TESLA_SUPERCHARGER",
                network_id=station["locationId"],
                address=address,
                location=location,
                charging_points=charging_points,
                source=SourceFeature(
                    quality="CURATED",
                    system="SUPERCHARGE",
                ),
                references=references,
            )

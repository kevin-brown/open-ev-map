from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

import scrapy

from collections import defaultdict


class ShellRechargeSpider(scrapy.Spider):
    name = "shellrecharge"

    PLUG_TYPE_TO_PLUG_MAP = {
        "SAEJ1772": "J1772_CABLE",
        "CCS": "J1772_COMBO",
        "CHAdeMO": "CHADEMO",

        "Combo Type 2 DC": None,
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

                    "EVC",
                    "EVG",
                    "FL2",
                ]
            },
            method="POST",
        )

    def parse(self, response):
        stations = response.json()["data"]

        for station in stations:
            if station["cpoId"] == "GRL":
                yield self.parse_station_greenlots(station)
            elif station["cpoId"] == "EVC":
                yield self.parse_station_evconnect(station)
            elif station["cpoId"] == "EVG":
                yield self.parse_station_evgo(station)
            elif station["cpoId"] == "FL2":
                yield self.parse_station_flo(station)
            else:
                raise

    def parse_station_evconnect(self, station):
        parsed_station = self.parse_base_station(station)

        parsed_station["network"] = "EV_CONNECT"
        parsed_station["network_id"] = station["locationId"][4:]

        parsed_station["source"] = SourceFeature(
            quality="PARTNER",
            system="SHELL_RECHARGE_GREENLOTS",
        )

        charging_points = {}

        charging_point_evses = defaultdict(list)

        for station_evse in station["evses"]:
            for connector in station_evse["ports"]:
                power = PowerFeature(
                    amperage=int(connector["current"]),
                    voltage=connector["voltage"],
                    output=int(connector["maxElectricPower"]),
                )

                plug = ChargingPortFeature(
                    plug=self.PLUG_TYPE_TO_PLUG_MAP[connector["plugType"]],

                    power=power,
                )

                evse_id = station_evse["evseEmaid"]

                evse = EvseFeature(
                    plugs=[plug],
                    network_id=evse_id,
                )

                charging_point_evses[station_evse["evseDisplayId"]].append(evse)

            charging_points[station_evse["evseDisplayId"]] = ChargingPointFeature(
                name=station_evse["evseDisplayId"],
                location=parsed_station["location"],
            )

        for charging_point_name, evses in charging_point_evses.items():
            charging_points[charging_point_name]["evses"] = evses

        parsed_station["charging_points"] = list(charging_points.values())

        return parsed_station

    def parse_station_evgo(self, station):
        parsed_station = self.parse_base_station(station)

        parsed_station["network"] = "EVGO"
        parsed_station["network_id"] = station["locationId"][4:]

        parsed_station["source"] = SourceFeature(
            quality="PARTNER",
            system="SHELL_RECHARGE_GREENLOTS",
        )
        charging_points = {}

        charging_point_evses = defaultdict(list)
        evse_plugs = defaultdict(list)

        for station_evse in station["evses"]:

            for connector in station_evse["ports"]:
                power = PowerFeature(
                    amperage=int(connector["current"]),
                    voltage=connector["voltage"],
                    output=int(connector["maxElectricPower"]),
                )

                plug = ChargingPortFeature(
                    plug=self.PLUG_TYPE_TO_PLUG_MAP[connector["plugType"]],

                    power=power,
                )

                evse_id = station_evse["evseEmaid"]

                if evse_id not in evse_plugs:
                    evse = EvseFeature(
                        network_id=evse_id,
                    )

                    charging_point_evses[station_evse["evseDisplayId"]].append(evse)

                evse_plugs[evse_id].append(plug)

            charging_points[station_evse["evseDisplayId"]] = ChargingPointFeature(
                name=station_evse["evseDisplayId"],
                location=parsed_station["location"],
            )

        for charging_point_name, evses in charging_point_evses.items():
            charging_points[charging_point_name]["evses"] = evses

            for evse in evses:
                evse["plugs"] = evse_plugs[evse["network_id"]]

        parsed_station["charging_points"] = list(charging_points.values())

        return parsed_station

    def parse_station_flo(self, station):
        parsed_station = self.parse_base_station(station)

        parsed_station["network"] = "FLO"
        parsed_station["network_id"] = station["locationId"][4:]

        parsed_station["source"] = SourceFeature(
            quality="PARTNER",
            system="SHELL_RECHARGE_GREENLOTS",
        )

        charging_points = []

        for station_evse in station["evses"]:
            evses = []

            plugs_for_evse = defaultdict(list)

            for connector in station_evse["ports"]:
                power = PowerFeature(
                    amperage=int(connector["current"]),
                    voltage=connector["voltage"],
                    output=int(connector["maxElectricPower"]),
                )

                plug = ChargingPortFeature(
                    plug=self.PLUG_TYPE_TO_PLUG_MAP[connector["plugType"]],

                    power=power,
                )

                evse_id = station_evse["evseEmaid"]

                plugs_for_evse[evse_id].append(plug)

            for evse_id, plugs in plugs_for_evse.items():
                evse = EvseFeature(
                    plugs=plugs,
                    network_id=evse_id,
                )

                evses.append(evse)

            charging_point = ChargingPointFeature(
                name=station_evse["evseDisplayId"],
                location=parsed_station["location"],
                evses=evses,
            )
            charging_points.append(charging_point)

        parsed_station["charging_points"] = charging_points

        return parsed_station

    def parse_station_greenlots(self, station):
        parsed_station = self.parse_base_station(station)

        parsed_station["network"] = "SHELL_RECHARGE"
        parsed_station["network_id"] = station["locationId"]

        parsed_station["source"] = SourceFeature(
            quality="ORIGINAL",
            system="SHELL_RECHARGE_GREENLOTS",
        )

        charging_points = []

        for station_evse in station["evses"]:
            evses = []

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

                evse_id = station_evse["evseEmaid"]

                if len(station_evse["ports"]) > 1:
                    evse_id += f"*{connector["portName"]}"

                evse = EvseFeature(
                    plugs=[plug],
                    network_id=evse_id,
                )

                evses.append(evse)

            hardware = HardwareFeature(
                manufacturer=station_evse["evseManufacturerName"],
                model=station_evse["evseModelName"],
            )

            charging_point = ChargingPointFeature(
                name=station_evse["evseDisplayId"],
                network_id=station_evse["evseEmaid"],
                location=parsed_station["location"],
                evses=evses,
                hardware=hardware,
            )
            charging_points.append(charging_point)

        parsed_station["charging_points"] = charging_points

        return parsed_station

    def parse_base_station(self, station):
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

        return StationFeature(
            name=station["name"],
            location=location,
            address=address,
        )

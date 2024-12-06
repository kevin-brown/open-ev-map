from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature
from scrapers.utils import MAPPER_STATE_ABBR_LONG_TO_SHORT, MAPPER_STATE_ABBR_SHORT_TO_LONG

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

                    "CPI",
                    "EVC",
                    "EVG",
                    "FLO",
                    "FL2",

                    "PRO",
                ]
            },
            method="POST",
        )

    def parse(self, response):
        stations = response.json()["data"]

        for station in stations:
            if station["state"] != "Massachusetts":
                continue

            if station["cpoId"] == "GRL":
                yield self.parse_station_greenlots(station)
            elif station["cpoId"] == "CPI":
                yield self.parse_station_chargepoint(station)
            elif station["cpoId"] == "EVC":
                yield self.parse_station_evconnect(station)
            elif station["cpoId"] == "EVG":
                yield self.parse_station_evgo(station)
            elif station["cpoId"] in ["FLO", "FL2"]:
                yield self.parse_station_flo(station)
            elif station["cpoId"] == "PRO":
                yield self.parse_station_ford_pro(station)
            else:
                print(station)
                raise

    def parse_station_chargepoint(self, station):
        parsed_station = self.parse_base_station(station)

        network_id = station["locationId"][4:]
        network_id = f"{network_id[0:2]}*{network_id[2:5]}*{network_id[5:]}"

        parsed_station["network"] = "CHARGEPOINT"
        parsed_station["network_id"] = network_id

        parsed_station["source"] = SourceFeature(
            quality="PARTNER",
            system="SHELL_RECHARGE_GREENLOTS",
        )
        charging_point = ChargingPointFeature(
            name=station["name"],
            location=parsed_station["location"],
            network_id=f"{network_id[0:7]}E{network_id[8:]}",
        )

        evses = []

        for station_evse in station["evses"]:
            plugs = []

            evse_id = station_evse["evseEmaid"]
            evse_id = f"{evse_id[0:2]}*{evse_id[2:5]}*{evse_id[5:]}"

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

                plugs.append(plug)

            evse = EvseFeature(
                network_id=evse_id,
                plugs=plugs,
            )

            evses.append(evse)

        charging_point["evses"] = evses

        parsed_station["charging_points"] = [charging_point]

        return parsed_station

    def parse_station_evconnect(self, station):
        parsed_station = self.parse_base_station(station)

        NETWORK_MAP = {
            "EV Connect": "EV_CONNECT",
            "SKYCHARGER": "SKYCHARGER",
            "ChargeSmart EV": "CHARGESMART_EV",
        }

        parsed_station["network"] = NETWORK_MAP[station["networkOperator"]["name"]]
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

                country_code = evse_id[0:2].upper()
                cpo_id = evse_id[3:6].upper()
                evse_identifier = evse_id[7:]

                evse_id = f"{country_code}*{cpo_id}*{evse_identifier}"

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

    def parse_station_ford_pro(self, station):
        parsed_station = self.parse_base_station(station)

        parsed_station["network"] = "FORD_CHARGE"
        parsed_station["network_id"] = station["locationId"][4:]

        parsed_station["source"] = SourceFeature(
            quality="PARTNER",
            system="SHELL_RECHARGE_GREENLOTS",
        )

        charging_points = {}

        charging_point_evses = defaultdict(list)

        for station_evse in station["evses"]:
            charger_name = station_evse["evseDisplayId"]

            if "-" in charger_name:
                charger_name = charger_name.rsplit("-", 1)[0]
            elif "_" in charger_name:
                if charger_name.count("_") > 1:
                    charger_prefix, charger_suffix, _ = charger_name.split("_", 2)
                    charger_name = f"{charger_prefix}_{charger_suffix}"

            charging_point_id = station_evse["evseEmaid"].rsplit("*", 1)[0]

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

                evse = EvseFeature(
                    plugs=[plug],
                    network_id=station_evse["evseEmaid"],
                )

                charging_point_evses[charging_point_id].append(evse)

            charging_points[charging_point_id] = ChargingPointFeature(
                name=charger_name,
                location=parsed_station["location"],
                network_id=charging_point_id,
            )

        for charging_point_id, evses in charging_point_evses.items():
            charging_points[charging_point_id]["evses"] = evses

        parsed_station["charging_points"] = list(charging_points.values())

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

        if state := station["state"]:
            if state.upper() in MAPPER_STATE_ABBR_SHORT_TO_LONG:
                state = state.upper()
            else:
                state = MAPPER_STATE_ABBR_LONG_TO_SHORT[state]

        address = AddressFeature(
            street_address=station["address"],
            city=station["city"],
            state=state,
            zip_code=station["zipCode"],
        )

        return StationFeature(
            name=station["name"],
            location=location,
            address=address,
        )

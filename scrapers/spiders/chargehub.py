from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, ReferenceFeature, SourceFeature, StationFeature

import reverse_geocode
import scrapy

from collections import defaultdict
from urllib.parse import urlencode


class ChargeHubSpider(scrapy.Spider):
    name = "chargehub"

    PLUG_CODE_TO_PLUG_TYPE = {
        4: ["CHADEMO"],
        5: ["J1772_CABLE"],
        6: ["J1772_COMBO"],
        7: ["NACS"],
        8: ["CHADEMO", "J1772_COMBO"],
        9: ["NACS"],
        11: ["J1772_COMBO", "J1772_COMBO"],
        12: ["J1772_COMBO", "NACS"],
    }

    def start_requests(self):
        query = {
            "remove_levels": 1,
            "amenities": "",
            "lonmin": -73.6,
            "lonmax": -69.6,
            "latmin": 41.0,
            "latmax": 43.0,
            "km": None,
            "remove_connectors": "1,2,3,8",
            "only_passport": 0,
            "show_pending": 0,
            "above_power": 0,
            "only_247": "",
            "limit": 2500,
            "remove_networks": "76,61,114,15,14,27,96,109,2,75,64,65,4,52,106,47,102,101,73,23,37,100,90,86,62,18,105,54,74,43,20,77,72,35,83,38,45,104,125,59,41,39,48,69,97,78,107,49,121,98,34,70,127,118,89,108,21,53,17,30,123,55,58,91,9,32,50,112,99,95,40,120,117,92,80,122,79,128,68,11,126,33,56,0,93,115,110,25",
            "free": "",
            "key": "olitest",
            "polyline": "",
            "language": "en",
        }

        yield scrapy.http.JsonRequest(
            url="https://apiv2.chargehub.com/api/locationsmap/v2?" + urlencode(query),
            callback=self.parse_locations,
        )
    
    def parse_locations(self, response):
        locations = response.json()["locationsArray"]

        for location in locations:
            geocode_data = reverse_geocode.get((location["Lat"], location["Long"]))

            if geocode_data["country_code"] != "US":
                continue

            if "state" in geocode_data and geocode_data["state"] != "Massachusetts":
                continue

            if location["NetString"] not in ["AmpUp", "Tesla", "Autel", "Blink", "Flo", "Shell Recharge", "Ford Charge", "ChargeLab", "ChargeSmartEV", "Red E", "Independent Operators", "Loop", "SWTCH", "TurnOnGreen", "Enel X Way", "Eaton", "EVConnect", "evGateway", "EVgo", "Electrify America"]:
                print(location["NetString"])
                continue

            query = {
                "station_id": location["LocID"],
                "language": "en",
                "isShared": False,
                "isTest": 0,
            }

            yield scrapy.http.JsonRequest(
                url="https://apiv2.chargehub.com/api/stations/details?" + urlencode(query),
                callback=self.parse_location_details,
            )

    def parse_location_details(self, response):
        location = response.json()["station"]

        if location["prov_state"] != "MA":
            return

        NETWORK_PARSERS = {
            "AmpUp": self.parse_station_amp_up,
            "Autel": self.parse_station_autel,
            "Blink": self.parse_station_blink,
            "ChargeLab": self.parse_station_charge_lab,
            "ChargeSmartEV": self.parse_station_charge_smart_ev,
            "Eaton": self.parse_station_eaton,
            "Electrify America": self.parse_station_electrify_america,
            "Enel X Way": self.parse_station_enel_x,
            "EVConnect": self.parse_ev_connect,
            "evGateway": self.parse_station_evgateway,
            "EVgo": self.parse_station_evgo,
            "Flo": self.parse_station_flo,
            "Ford Charge": self.parse_station_ford_charge,
            "Independent Operators": self.parse_station_shell_recharge,
            "Loop": self.parse_station_loop,
            "Red E": self.parse_station_red_e,
            "Shell Recharge": self.parse_station_shell_recharge,
            "SWTCH": self.parse_station_swtch,
            "Tesla": self.parse_station_tesla,
            "TurnOnGreen": self.parse_station_turn_on_green,
        }

        for plug in location["PlugsArray"]:
            network_name = plug["NetworkName"]

            if network_name == "None":
                continue
        
            if network_name not in NETWORK_PARSERS:
                print(f"Could not find parser for: {network_name}")
                continue

            yield from NETWORK_PARSERS[network_name](location, plug)

    def parse_base_station(self, location):
        source = SourceFeature(
            system="CHARGE_HUB",
            quality="AGGREGATED",
        )

        coordinates = LocationFeature(
            latitude=location["Lat"],
            longitude=location["Long"],
        )

        address = AddressFeature(
            street_address=f"{location["StreetNo"]} {location["Street"]}",
            city=location["City"],
            state=location["prov_state"],
            zip_code=location["Zip"],
        )

        return StationFeature(
            name=location["LocName"],
            source=source,
            location=coordinates,
            address=address,
            references=[
                ReferenceFeature(
                    system="CHARGE_HUB",
                    identifier=location["IdAsString"],
                )
            ]
        )

    def parse_power_for_plug(self, plug):
        power = PowerFeature()

        if voltage := plug.get("Volt"):
            power["voltage"] = int(voltage.split(" ")[0])

        if amperage := plug.get("Amp"):
            power["amperage"] = int(amperage.split(" ")[0])

        if output := plug.get("Kw"):
            power["output"] = int(float(output.split(" ")[0]) * 1000)

        return power

    def parse_plugs(self, plug):
        plugs = []

        for plug_type in self.PLUG_CODE_TO_PLUG_TYPE[plug["Code"]]:
            plugs.append(
                ChargingPortFeature(
                    plug=plug_type,
                    power=self.parse_power_for_plug(plug),
                ),
            )

        return plugs

    def parse_station_amp_up(self, location, plug):
        print(location)

        station = self.parse_base_station(location)

        station["network"] = "AMP_UP"

        yield station

    def parse_station_autel(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "AUTEL"

        charging_points = []

        for plug_type in self.PLUG_CODE_TO_PLUG_TYPE[plug["Code"]]:
            for port in plug["Ports"]:
                charging_points.append(
                    ChargingPointFeature(
                        evses=[
                            EvseFeature(
                                plugs=[
                                    ChargingPortFeature(
                                        plug=plug_type,
                                        power=self.parse_power_for_plug(plug),
                                    ),
                                ],
                            )
                        ]
                    )
                )

        station["charging_points"] = charging_points

        yield station

    def parse_station_blink(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "BLINK"

        charging_points = []

        for port in plug["Ports"]:
            charging_point_id = None

            if port["displayName"].startswith("BAE"):
                charging_point_id = f"US*BLK*E{port["displayName"]}"

            charging_points.append(
                ChargingPointFeature(
                    name=port["displayName"],
                    network_id=charging_point_id,
                    evses=[
                        EvseFeature(
                            network_id=port["netPortId"],
                            plugs=self.parse_plugs(plug),
                        )
                    ]
                )
            )

        station["charging_points"] = charging_points

        yield station

    def parse_station_charge_lab(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "CHARGE_LAB"

        charging_points = []

        for port in plug["Ports"]:
            plugs = []

            charging_points.append(
                ChargingPointFeature(
                    network_id=port["netPortId"].split("*", 1)[0],
                    evses=[
                        EvseFeature(
                            network_id=port["netPortId"],
                            plugs=self.parse_plugs(plug),
                        ),
                    ],
                )
            )

        station["charging_points"] = charging_points

        yield station

    def parse_station_charge_smart_ev(self, location, plug):
        print(location)

        station = self.parse_base_station(location)

        station["network"] = "CHARGESMART_EV"

        yield station

    def parse_station_eaton(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "EATON"

        charging_point_evses = defaultdict(list)
        charging_points = {}

        for port in plug["Ports"]:
            if "_" not in port["displayName"]:
                continue

            point_name = port["displayName"].rsplit("_", 1)[0]

            charging_point_evses[point_name].append(
                EvseFeature(
                    plugs=self.parse_plugs(plug),
                )
            )

            charging_points[point_name] = ChargingPointFeature(
                name=point_name,
            )

        for charging_point_name, evses in charging_point_evses.items():
            charging_points[charging_point_name]["evses"] = evses

        station["charging_points"] = list(charging_points.values())

        yield station

    def parse_station_electrify_america(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "ELECTRIFY_AMERICA"

        yield station

    def parse_station_enel_x(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "ENEL_X"

        yield station

    def parse_ev_connect(self, location, plug):
        station = self.parse_base_station(location)

        if "SKYCHARGER" in station["name"]:
            station["network"] = "SKYCHARGER"
            station["name"] = ""
        else:
            station["network"] = "EV_CONNECT"

        charging_point_evses = defaultdict(list)
        charging_points = {}

        for port in plug["Ports"]:
            point_name = port["displayName"]

            if "Port" in point_name:
                point_name = ""

            evse_id = f"US*EVC*E{port["netPortId"]}"

            if not port["netPortId"]:
                evse_id = ""

            charging_point_evses[point_name].append(
                EvseFeature(
                    plugs=self.parse_plugs(plug),
                    network_id=evse_id,
                )
            )

            charging_points[point_name] = ChargingPointFeature(
                name=point_name,
            )

        for charging_point_name, evses in charging_point_evses.items():
            charging_points[charging_point_name]["evses"] = evses

        station["charging_points"] = list(charging_points.values())

        yield station

    def parse_station_evgateway(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "EV_GATEWAY"

        charging_point_evses = defaultdict(list)
        charging_points = {}

        for port in plug["Ports"]:
            if "_" not in port["displayName"]:
                continue

            point_name = port["displayName"].rsplit("_", 1)[0]

            charging_point_evses[point_name].append(
                EvseFeature(
                    plugs=self.parse_plugs(plug),
                )
            )

            charging_points[point_name] = ChargingPointFeature(
                name=point_name,
            )

        for charging_point_name, evses in charging_point_evses.items():
            charging_points[charging_point_name]["evses"] = evses

        station["charging_points"] = list(charging_points.values())

        yield station

    def parse_station_evgo(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "EVGO"

        yield station

    def parse_station_ford_charge(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "FORD_CHARGE"

        yield station

    def parse_station_flo(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "FLO"

        charging_points = []

        country_code = location["Country"][:2].upper()
        cpo_id = "FLO" if country_code == "CA" else "FL2"

        for port in plug["Ports"]:
            plugs = []

            charging_points.append(
                ChargingPointFeature(
                    name=port["displayName"],
                    network_id=f"{country_code}*{cpo_id}*E{port["displayName"]}",
                    evses=[
                        EvseFeature(
                            network_id=f"{country_code}*{cpo_id}*E{port["displayName"]}*1",
                            plugs=self.parse_plugs(plug),
                        ),
                    ],
                )
            )

        station["charging_points"] = charging_points

        yield station

    def parse_station_loop(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "LOOP"

        yield station

    def parse_station_red_e(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "RED_E"

        charging_points = {}
        charging_points_to_evses = defaultdict(list)

        for port in plug["Ports"]:
            point_name = port["displayName"].rsplit("-", 1)[0]
            charging_point_id = port["netPortId"].rsplit("*")[0]

            charging_points_to_evses[charging_point_id].append(
                EvseFeature(
                    plugs=self.parse_plugs(plug),
                    network_id=port["netPortId"],
                )
            )

            charging_points[charging_point_id] = ChargingPointFeature(
                name=point_name,
                network_id=charging_point_id,
            )
        
        for charging_point_id, evses in charging_points_to_evses.items():
            charging_points[charging_point_id]["evses"] = evses

        station["charging_points"] = list(charging_points.values())

        yield station

    def parse_station_shell_recharge(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "SHELL_RECHARGE"

        charging_points = []

        for port in plug["Ports"]:
            plugs = []

            charging_points.append(
                ChargingPointFeature(
                    name=port["displayName"],
                    evses=[
                        EvseFeature(
                            network_id=port["netPortId"],
                            plugs=self.parse_plugs(plug),
                        ),
                    ],
                )
            )

        station["charging_points"] = charging_points

        yield station

    def parse_station_swtch(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "SWTCH"

        charging_points = []

        for port in plug["Ports"]:
            plugs = []

            charging_points.append(
                ChargingPointFeature(
                    name=port["displayName"],
                    evses=[
                        EvseFeature(
                            network_id=f"CA*SWT*E{port["netPortId"]}",
                            plugs=self.parse_plugs(plug),
                        ),
                    ],
                )
            )

        station["charging_points"] = charging_points

        yield station

    def parse_station_tesla(self, location, plug):
        station = self.parse_base_station(location)

        if plug["Level"] == 2:
            station["network"] = "TESLA_DESTINATION"
        else:
            station["network"] = "TESLA_SUPERCHARGER"

        charging_points = []

        for port in plug["Ports"]:
            if "netPortId" not in port:
                continue

            network_id = port["netPortId"].split("_")[0]

            charging_points.append(
                ChargingPointFeature(
                    evses=[
                        EvseFeature(
                            network_id=port["netPortId"].replace("_", "*"),
                            plugs=self.parse_plugs(plug),
                        ),
                    ],
                )
            )

        if network_id is not None:
            station["network_id"] = network_id

        station["charging_points"] = charging_points

        yield station

    def parse_station_turn_on_green(self, location, plug):
        station = self.parse_base_station(location)

        station["network"] = "TURN_ON_GREEN"

        charging_points = []

        for port in plug["Ports"]:
            plugs = []

            charging_points.append(
                ChargingPointFeature(
                    network_id=port["netPortId"].split("*", 1)[0],
                    evses=[
                        EvseFeature(
                            network_id=port["netPortId"],
                            plugs=self.parse_plugs(plug),
                        ),
                    ],
                )
            )

        station["charging_points"] = charging_points

        yield station

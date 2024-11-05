from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, ReferenceFeature, SourceFeature, StationFeature

from scrapy.utils.project import get_project_settings
import scrapy

from collections import defaultdict
from urllib.parse import urlencode


class NrelAlternativeFuelDataCenterSpider(scrapy.Spider):
    name = "nrel_afdc"

    NETWORK_MAP = {
        "7CHARGE": "SEVEN_CHARGE",
        "ABM": "ABM",
        "AMPED_UP": "AMPED_UP",
        "AMPUP": "AMP_UP",
        "Blink Network": "BLINK",
        "CHARGELAB": "CHARGE_LAB",
        "ChargePoint Network": "CHARGEPOINT",
        "CHARGESMART_EV": None,
        "Electrify America": "ELECTRIFY_AMERICA",
        "EV Connect": "EV_CONNECT",
        "EVGATEWAY": "EV_GATEWAY",
        "eVgo Network": "EVGO",
        "FORD_CHARGE": "FORD_CHARGE",
        "FLO": "FLO",
        "LIVINGSTON": None,
        "LOOP": "LOOP",
        "NOODOE": "NOODOE",
        "Non-Networked": "NON_NETWORKED",
        "OpConnect": None,
        "POWER_NODE": "ELECTRIC_ERA",
        "RED_E": "RED_E",
        "RIVIAN_ADVENTURE": "RIVIAN_ADVENTURE",
        "SHELL_RECHARGE": "SHELL_RECHARGE",
        "SWTCH": None,
        "Tesla": "TESLA_SUPERCHARGER",
        "Tesla Destination": "TESLA_DESTINATION",
        "TURNONGREEN": "TURN_ON_GREEN",
        "Volta": "VOLTA",
    }

    CONNECTOR_TO_PLUG_MAP = {
        "CHADEMO": "CHADEMO",
        "TESLA": "NACS",
        "J1772": "J1772_CABLE",
        "J1772COMBO": "J1772_COMBO",
    }

    def start_requests(self):
        settings = get_project_settings()

        query = {
            "api_key": settings.get('NREL_API_KEY'),
            "fuel_type": "ELEC",
            "state": "MA",
            "ev_connector_type": "TESLA,J1772,J1772COMBO,CHADEMO",
        }

        yield scrapy.http.JsonRequest(
            url="https://developer.nrel.gov/api/alt-fuel-stations/v1.json?" + urlencode(query),
        )

    def parse(self, response):
        CHARGING_POINTS_PARSER = {
            "CHARGEPOINT": self.parse_charging_points_chargepoint,
            "ELECTRIC_ERA": self.parse_charging_points_electric_era,
            "ELECTRIFY_AMERICA": self.parse_charging_points_electrify_america,
            "EV_CONNECT": self.parse_charging_points_ev_connect,
            "FLO": self.parse_charging_points_flo,
            "RIVIAN_ADVENTURE": self.parse_charging_points_rivian_adventure,
            "SHELL_RECHARGE": self.parse_charging_points_shell_recharge,
        }

        NETWORK_ID_PARSER = {
            "CHARGEPOINT": self.parse_network_id_chargepoint,
            "ELECTRIFY_AMERICA": self.parse_network_id_first,
            "EV_CONNECT": self.parse_network_id_first,
            "FLO": self.parse_network_id_first,
            "SHELL_RECHARGE": self.parse_network_id_first,
        }

        stations = response.json()["fuel_stations"]

        for station in stations:
            references = []

            references.append(
                ReferenceFeature(
                    identifier=station["id"],
                    system="ALTERNATIVE_FUEL_DATA_CENTER",
                )
            )

            coordinates = LocationFeature(
                latitude=station["latitude"],
                longitude=station["longitude"],
            )

            address = AddressFeature(
                street_address=station["street_address"],
                city=station["city"],
                state=station["state"],
                zip_code=station["zip"].rjust(5, "0"),
            )

            network = self.NETWORK_MAP[station["ev_network"]]

            if network in NETWORK_ID_PARSER:
                network_id = NETWORK_ID_PARSER[network](station)
            else:
                network_id = ""

            if network in CHARGING_POINTS_PARSER:
                charging_points = CHARGING_POINTS_PARSER[network](station)
            else:
                charging_points = []

            if station["nps_unit_name"]:
                station_name = station["nps_unit_name"]
            else:
                station_name = station["station_name"]

            yield StationFeature(
                name=station_name,
                address=address,
                location=coordinates,
                network=network,
                network_id=network_id,
                charging_points=charging_points,
                references=references,
                source=SourceFeature(
                    quality="AGGREGATED",
                    system="ALTERNATIVE_FUEL_DATA_CENTER",
                ),
            )

    def parse_charging_points_chargepoint(self, station):
        connector_types = station["ev_connector_types"]

        if l2_count := station["ev_level2_evse_num"]:
            evses = []

            if "ev_network_ids" in station:
                if "NEMA515" in connector_types:
                    return []

                station_ids = station["ev_network_ids"]["station"]

                if len(station_ids) > 1:
                    print(station)
                    raise

                cp_id = station_ids[0][6:]

                plugs = []

                for connector_type in connector_types:
                    plugs.append(
                        ChargingPortFeature(
                            plug=self.CONNECTOR_TO_PLUG_MAP[connector_type],
                        )
                    )

                for i in range(l2_count):
                    evses.append(
                        EvseFeature(
                            plugs=plugs,
                            network_id=f"US*CPI*E{cp_id}*{i+1}"
                        )
                    )

            charging_point = ChargingPointFeature(
                name=station["station_name"],
                evses=evses,
            )

            return [charging_point]

        return []

    def parse_charging_points_electric_era(self, station):
        charging_points = []

        for _ in range(station["ev_dc_fast_num"] // 2):
            charging_points.append(
                ChargingPointFeature(
                    evses=[
                        EvseFeature(
                            plugs=[
                                ChargingPortFeature(
                                    plug="J1772_COMBO",
                                ),
                            ],
                        ),
                        EvseFeature(
                            plugs=[
                                ChargingPortFeature(
                                    plug="J1772_COMBO",
                                ),
                            ],
                        ),
                    ]
                )
            )

        return charging_points

    def parse_charging_points_electrify_america(self, station):
        charging_points = []

        for post_id in station["ev_network_ids"]["posts"]:
            charging_points.append(
                ChargingPointFeature(
                    network_id=post_id,
                )
            )

        return charging_points

    def parse_charging_points_ev_connect(self, station):
        if "ev_network_ids" not in station:
            print(station)
            raise

        connector_types = station["ev_connector_types"]

        post_ids = station["ev_network_ids"]["posts"]

        if l2_count := station["ev_level2_evse_num"]:
            charging_points = []

            if "ev_network_ids" in station:
                station_ids = station["ev_network_ids"]["station"]

                if len(station_ids) > 1:
                    print(station)
                    raise

                plugs = []

                for connector_type in connector_types:
                    plugs.append(
                        ChargingPortFeature(
                            plug=self.CONNECTOR_TO_PLUG_MAP[connector_type],
                        )
                    )

                for post_id in post_ids:
                    charging_points.append(
                        ChargingPointFeature(
                            evses=[
                                EvseFeature(
                                    plugs=plugs,
                                    network_id=f"US*EVC*E{post_id}"
                                ),
                            ],
                        )

                    )

            return charging_points

        return []

    def parse_charging_points_flo(self, station):
        connector_types = station["ev_connector_types"]

        if l2_count := station["ev_level2_evse_num"]:
            charging_points = []

            if "ev_network_ids" in station:
                station_ids = station["ev_network_ids"]["station"]

                if len(station_ids) > 1:
                    print(station)
                    raise

                plugs = []

                for connector_type in connector_types:
                    plugs.append(
                        ChargingPortFeature(
                            plug=self.CONNECTOR_TO_PLUG_MAP[connector_type],
                        )
                    )

                for i in range(l2_count):
                    charging_point = ChargingPointFeature(
                        evses=[
                            EvseFeature(
                                plugs=plugs,
                            ),
                        ],
                    )

                    charging_points.append(charging_point)

            return charging_points

        return []

    def parse_charging_points_rivian_adventure(self, station):
        connector_types = station["ev_connector_types"]
        plugs = []

        for connector_type in connector_types:
            plugs.append(
                ChargingPortFeature(
                    plug=self.CONNECTOR_TO_PLUG_MAP[connector_type],
                )
            )

        charging_point_name = station["station_name"].split("(", 1)[1][:-1]

        return [
            ChargingPointFeature(
                name=charging_point_name,
                network_id=station["ev_network_ids"]["station"][0],
                evses=[
                    EvseFeature(
                        plugs=plugs,
                        network_id=station["ev_network_ids"]["posts"][0],
                    )
                ],
                hardware=HardwareFeature(
                    brand="RIVIAN",
                )
            )
        ]

    def parse_charging_points_shell_recharge(self, station):
        if "ev_network_ids" not in station:
            print(station)
            raise

        connector_types = station["ev_connector_types"]

        if len(connector_types) > 1:
            print(station)
            raise

        post_ids = station["ev_network_ids"]["posts"]

        if l2_count := station["ev_level2_evse_num"]:
            charging_points = []

            post_id_groups = defaultdict(list)

            for post_id in post_ids:
                if "*" in post_id:
                    prefix, _ = post_id.split("*")
                    post_id_groups[prefix].append(post_id)
                else:
                    post_id_groups[post_id].append(post_id)

            for charging_point_id, evse_ids in post_id_groups.items():
                evses = []

                for evse_id in evse_ids:
                    plugs = []

                    for connector_type in connector_types:
                        plugs.append(
                            ChargingPortFeature(
                                plug=self.CONNECTOR_TO_PLUG_MAP[connector_type],
                            )
                        )

                    evses.append(
                        EvseFeature(
                            plugs=plugs,
                            network_id=evse_id,
                        )
                    )

                charging_points.append(
                    ChargingPointFeature(
                        evses=evses,
                        network_id=charging_point_id,
                    )
                )

            return charging_points

        return []

    def parse_network_id_first(self, station):
        if "ev_network_ids" not in station:
            return ""

        station_ids = station["ev_network_ids"]["station"]

        if len(station_ids) > 1:
            print(station)
            raise

        return station_ids[0]

    def parse_network_id_chargepoint(self, station):
        if "ev_network_ids" not in station:
            return ""

        station_ids = station["ev_network_ids"]["station"]

        if len(station_ids) > 1:
            print(station)
            raise

        cp_id = station_ids[0][6:]

        return f"US*CPI*L{cp_id}"

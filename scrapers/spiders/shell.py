from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature
from scrapers.utils import MAPPER_STATE_ABBR_LONG_TO_SHORT, MAPPER_STATE_ABBR_SHORT_TO_LONG

from scrapy.utils.project import get_project_settings
import scrapy

from collections import defaultdict
import uuid


class ShellSpider(scrapy.Spider):
    name = "shell"

    handle_httpstatus_list = [200, 401]

    PLUG_TYPE_TO_PLUG_MAP = {
        "SAEJ1772": "J1772_CABLE",
        "CCS": "J1772_COMBO",
        "CHAdeMO": "CHADEMO",

        "IEC_62196_T1": "J1772_CABLE",
        "IEC_62196_T1_COMBO": "J1772_COMBO",
        "CHADEMO": "CHADEMO",
    }

    def start_requests(self):
        settings = get_project_settings()

        refresh_token = settings.get("SHELL_API_KEY")

        yield scrapy.http.FormRequest(
            url="https://api.shell.com/oauth/v1/mobility/token",
            formdata={
                "grant_type": "client_credentials",
            },
            headers={
                "Authorization": f"Basic {refresh_token}",
            },
            callback=self.parse_token,
        )

    def parse_token(self, response):
        data = response.json()

        access_token = data["access_token"]

        query = """
        {
            getNearbyLocationsByDistance(input: {
                centerPoint: {
                    latitude: 42.13,
                    longitude: -71.76
                },
                radialDistanceKm: 400,
                filteringDetails: {
                    limit: 250,
                    partyId: "{party_id}",
                    containsConnectorTypes: [CCS, CHAdeMO, SAEJ1772]
                }
            }) {
                cpo_id
                id
                name
                address
                postal_code
                city
                province
                state
                country
                coordinates {
                    latitude
                    longitude
                }
                operator {
                    name
                }
                evses {
                    evse_id
                    physical_reference
                    status
                    connectors {
                        standard
                        voltage
                        amperage
                        max_electric_power
                        tariff_id
                        tariff {
                            add_on_fee {
                                name
                                description
                                amount
                                type
                                fee_charged
                            }
                            elements {
                                price_components {
                                    price
                                    type
                                }
                                restrictions {
                                    start_time
                                    end_time
                                    min_kwh
                                    max_kwh
                                    min_power
                                    max_power
                                    min_duration
                                    max_duration
                                    day_of_week
                                }
                                is_relevant_now
                            }
                        }
                    }
                }
                charging_when_closed,
                opening_times {
                    regular_hours {
                        weekday
                        period_begin
                        period_end
                    }
                    twentyfourseven
                }
                facilities
            }
        }
        """

        for party_id in ["EVG", "PRO"]:
            yield scrapy.http.JsonRequest(
                url="https://api.shell.com/DS-PT-MPP-ShellMobileCommerce-MppUSA/emob/query",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "RequestId": str(uuid.uuid4()),
                },
                data={
                    "query": query.replace("{party_id}", party_id),
                },
                meta={
                    "access_token": access_token,
                },
                callback=self.parse_locations,
            )

    def parse_locations(self, response):
        locations = response.json()["data"]["getNearbyLocationsByDistance"]

        for location in locations:
            if location["state"] != "Massachusetts":
                continue

            yield from self.parse_location(location)

    def parse_location(self, location):
        print(location)

        cpo_to_parser = {
            "EVG": self.parse_location_evg,
            "PRO": self.parse_location_pro,
        }

        if parser := cpo_to_parser.get(location["cpo_id"]):
            yield from parser(location)

    def parse_base_station(self, station):
        location = LocationFeature(
            **station["coordinates"],
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
            zip_code=station["postal_code"],
        )

        return StationFeature(
            name=station["name"],
            location=location,
            address=address,
        )

    def parse_location_evg(self, location):
        station = self.parse_base_station(location)

        station["network"] = "EVGO"
        station["network_id"] = location["id"][4:]

        station["source"] = SourceFeature(
            system="SHELL_MOBILE_COMMERCE",
            quality="PARTNER",
        )

        charging_points = {}

        charging_point_evses = defaultdict(list)
        evse_plugs = defaultdict(list)

        for station_evse in location["evses"]:
            charging_point_id = None

            for connector in station_evse["connectors"]:
                power = PowerFeature(
                    amperage=connector["amperage"],
                    voltage=connector["voltage"],
                    output=connector["max_electric_power"],
                )

                plug = ChargingPortFeature(
                    plug=self.PLUG_TYPE_TO_PLUG_MAP[connector["standard"]],

                    power=power,
                )

                evse_id = station_evse["evse_id"]
                charging_point_id = evse_id.rsplit("*", 1)[0]

                if evse_id not in evse_plugs:
                    evse = EvseFeature(
                        network_id=evse_id,
                    )

                    charging_point_evses[station_evse["physical_reference"]].append(evse)

                evse_plugs[evse_id].append(plug)

            charging_points[station_evse["physical_reference"]] = ChargingPointFeature(
                name=station_evse["physical_reference"],
                location=station["location"],
            )

            if charging_point_id:
                charging_points[station_evse["physical_reference"]]["network_id"] = charging_point_id

        for charging_point_name, evses in charging_point_evses.items():
            charging_points[charging_point_name]["evses"] = evses

            for evse in evses:
                evse["plugs"] = evse_plugs[evse["network_id"]]

        station["charging_points"] = list(charging_points.values())

        yield station

    def parse_location_pro(self, location):
        station = self.parse_base_station(location)

        station["network"] = "FORD_CHARGE"
        station["network_id"] = location["id"][4:]

        station["source"] = SourceFeature(
            system="SHELL_MOBILE_COMMERCE",
            quality="PARTNER",
        )

        charging_points = {}

        charging_point_evses = defaultdict(list)

        for station_evse in location["evses"]:
            charger_name = station_evse["physical_reference"]

            if "-" in charger_name:
                charger_name = charger_name.rsplit("-", 1)[0]
            elif "_" in charger_name:
                if charger_name.count("_") > 1:
                    charger_prefix, charger_suffix, _ = charger_name.split("_", 2)
                    charger_name = f"{charger_prefix}_{charger_suffix}"

            charging_point_id = station_evse["evse_id"].rsplit("*", 1)[0]

            for connector in station_evse["connectors"]:
                power = PowerFeature(
                    amperage=connector["amperage"],
                    voltage=connector["voltage"],
                    output=connector["max_electric_power"],
                )

                plug = ChargingPortFeature(
                    plug=self.PLUG_TYPE_TO_PLUG_MAP[connector["standard"]],

                    power=power,
                )

                evse = EvseFeature(
                    plugs=[plug],
                    network_id=station_evse["evse_id"],
                )

                charging_point_evses[charging_point_id].append(evse)

            charging_points[charging_point_id] = ChargingPointFeature(
                name=charger_name,
                location=station["location"],
                network_id=charging_point_id,
            )

        for charging_point_id, evses in charging_point_evses.items():
            charging_points[charging_point_id]["evses"] = evses

        station["charging_points"] = list(charging_points.values())

        yield station

from scrapy.utils.project import get_project_settings
import scrapy

from urllib.parse import urlencode

from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, LocationFeature, ReferenceFeature, StationFeature


class NrelAlternativeFuelDataCenterSpider(scrapy.Spider):
    name = "nrel_afdc"

    NETWORK_MAP = {
        "7CHARGE": "SEVEN_CHARGE",
        "ABM": "ABM",
        "AMPED_UP": "AMPED_UP",
        "AMPUP": "AMPUP",
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
        }

        NETWORK_ID_PARSER = {
            "CHARGEPOINT": self.parse_network_id_chargepoint,
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

    def parse_network_id_chargepoint(self, station):
        if "ev_network_ids" not in station:
            return ""

        station_ids = station["ev_network_ids"]["station"]

        if len(station_ids) > 1:
            print(station)
            raise

        cp_id = station_ids[0][6:]

        return f"US*CPI*L{cp_id}"

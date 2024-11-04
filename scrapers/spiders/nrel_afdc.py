from scrapy.utils.project import get_project_settings
import scrapy

from urllib.parse import urlencode

from scrapers.items import AddressFeature, LocationFeature, ReferenceFeature, StationFeature


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
            network_id = ""
            charging_points = []

            if network == "CHARGEPOINT":
                network_id = self.parse_network_id_chargepoint(station)

            yield StationFeature(
                name=station["station_name"],
                address=address,
                location=coordinates,
                network=network,
                network_id=network_id,
                charging_points=charging_points,
                references=references,
            )

    def parse_network_id_chargepoint(self, station):
        if "ev_network_ids" not in station:
            return ""

        station_ids = station["ev_network_ids"]["station"]

        if len(station_ids) > 1:
            print(station)
            raise

        cp_id = station_ids[0][6:]

        return f"US*CPI*L{cp_id}"

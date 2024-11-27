from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature
from scrapers.utils import MAPPER_STATE_ABBR_LONG_TO_SHORT

from geopy.exc import GeocoderUnavailable
from geopy.geocoders import Nominatim
from pyzipcode import ZipCodeDatabase
import scrapy

import json
import uuid


osm_geocoder = Nominatim(
    user_agent='Open EV Map (https://github.com/kevin-brown/open-ev-map)',
)

zip_search = ZipCodeDatabase()

class EvGatewaySpider(scrapy.Spider):
    name = "evgateway"
    org_id = 1
    network_name = "EV_GATEWAY"

    STANDARD_TO_PLUG_TYPE_MAP = {
        "IEC_62196_T1": "J1772_CABLE",
        "IEC_62196_T1_COMBO": "J1772_COMBO",
        "CHADEMO": "CHADEMO",
    }

    def start_requests(self):
        device_token = uuid.uuid4().hex

        yield scrapy.http.JsonRequest(
            url="https://mobileapi.evgateway.com/api/v3/info/nearMeStations",
            data={
                "capacity": [],
                "chargerType": [],
                "connectorType": [],
                "deviceToken": device_token,
                "filter": True,
                "lat": "42.13",
                "lng": "-71.76",
                "network": [
                    self.org_id,
                ],
                "networkString": [],
                "orgId": self.org_id,
                "price": {
                    "free": False,
                },
                "radius": 145,
                "siteId": 0,
                "status": [],
                "uuid": "",
            },
            meta={
                "device_token": device_token,
            },
            callback=self.parse_near_me,
        )

    def parse_near_me(self, response):
        yield scrapy.http.JsonRequest(
            url="https://mobileapi.evgateway.com/api/v3/info/filter",
            data={
                "capacity": [],
                "chargerType": [],
                "connectorType": [],
                "deviceToken": response.meta["device_token"],
                "filter": True,
                "lat": 0,
                "lng": 0,
                "network": [
                    self.org_id,
                ],
                "networkString": [],
                "orgId": self.org_id,
                "price": {
                    "free": False,
                },
                "radius": 145,
                "siteId": 0,
                "status": [],
                "uuid": "",
            },
            meta={
                "device_token": response.meta["device_token"],
            },
            callback=self.parse_locations,
        )

    def parse_locations(self, response):
        locations = response.json()["data"]

        for location in locations:
            yield scrapy.http.JsonRequest(
                url="https://mobileapi.evgateway.com/api/v3/info/siteDetails",
                data={
                    "capacity": [],
                    "chargerType": [],
                    "connectorType": [],
                    "deviceToken": response.meta["device_token"],
                    "filter": False,
                    "lat": location["latitude"],
                    "lng": location["longitude"],
                    "network": [],
                    "networkString": [],
                    "orgId": 1,
                    "price": {
                        "free": False,
                    },
                    "radius": 50,
                    "siteId": location["id"],
                    "status": [],
                    "uuid": "",
                },
                callback=self.parse_site,
            )

    def parse_site(self, response):
        location = response.json()["data"]

        if location is None:
            original_request = json.loads(response.request.body)

            if original_request["orgId"] == self.org_id:
                return

            original_request["orgId"] = self.org_id

            yield scrapy.http.JsonRequest(
                url="https://mobileapi.evgateway.com/api/v3/info/siteDetails",
                data=original_request,
                callback=self.parse_site,
            )

            return

        address_parts = location["address"].split()
        zip_code = None

        if address_parts[-1].replace("-", "").isdigit():
            zip_code = address_parts[-1]
            del address_parts[-1]

        try:
            geocode_data = osm_geocoder.geocode(" ".join(address_parts), exactly_one=True, addressdetails=True)
        except GeocoderUnavailable:
            geocode_data = None

        if geocode_data is None:
            zip_info = zip_search.get(zip_code)

            if zip_info is not None:
                address = AddressFeature(
                    state=zip_info.state,
                    zip_code=zip_code,
                )
            else:
                address = None
        else:
            address_parts = geocode_data.raw["address"]

            address = AddressFeature(
                state=MAPPER_STATE_ABBR_LONG_TO_SHORT[address_parts["state"]],
                zip_code=address_parts["postcode"],
            )

        coordinates = LocationFeature(
            latitude=location["latitude"],
            longitude=location["longitude"],
        )

        if not address or address["state"] != "MA":
            return

        charging_points = []

        for station in location["stations"]:
            evses = []

            for port in station["ports"]:
                evses.append(
                    EvseFeature(
                        network_id=port["id"],
                        plugs=[
                            ChargingPortFeature(
                                plug=self.STANDARD_TO_PLUG_TYPE_MAP[port["connectorType"]],
                                power=PowerFeature(
                                    output=int(port["capacity"] * 1000),
                                )
                            )
                        ]
                    )
                )

            charging_points.append(
                ChargingPointFeature(
                    name=station["name"],
                    network_id=station["id"],
                    evses=evses,
                )
            )

        yield StationFeature(
            name=location["name"],
            network=self.network_name,
            network_id=location["id"],
            location=coordinates,
            address=address,
            charging_points=charging_points,
            source=SourceFeature(
                quality="ORIGINAL",
                system="EV_GATEWAY",
            ),
        )

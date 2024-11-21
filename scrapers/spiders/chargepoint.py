from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

from uszipcode.state_abbr import MAPPER_STATE_ABBR_LONG_TO_SHORT
import scrapy

import json
import urllib


class ChargePointSpider(scrapy.Spider):
    name = "chargepoint"

    CONNECTOR_TYPE_TO_PLUG_TYPE_MAP = {
        "J1772": "J1772_CABLE",
        "CCS1": "J1772_COMBO",
        "CHAdeMO": "CHADEMO",
        "NACS": "NACS",
        "NACS (Tesla)": "NACS",
        "SAE-Combo-CCS1": "J1772_COMBO",

        "NEMA": None,
        "Combo": "J1772_COMBO",
        "SAE-Combo-CCS1": "J1772_COMBO",
    }

    def _filter_for_query(self):
        return {
            "price_free": False,
            "status_available": False,
            "dc_fast_charging": False,
            "disabled_parking": False,
            "van_accessible": False,
            "connector_my_EV": False,
            "network_bchydro": False,
            "network_blink": False,
            "network_chargepoint": True,
            "network_circuitelectric": False,
            "network_evconnect": False,
            "network_evgo": False,
            "network_flo": False,
            "network_greenlots": False,
            "network_mercedes": False,
            "network_semacharge": False,
            "connector_l1": False,
            "connector_l2": False,
            "connector_l2_nema_1450": False,
            "connector_l2_tesla": False,
            "connector_chademo": False,
            "connector_combo": False,
            "connector_tesla": False
        }

    def _map_query_for_bounding_box(self, sw_lon, sw_lat, ne_lon, ne_lat):
        return {
            "map_data": {
                "screen_width": 1150,
                "screen_height": 1255,
                "ne_lat": ne_lat,
                "ne_lon": ne_lon,
                "sw_lat": sw_lat,
                "sw_lon": sw_lon,
                "filter": self._filter_for_query(),
                "bound_output": True,
            }
        }

    def _station_query_for_bounding_box(self, sw_lon, sw_lat, ne_lon, ne_lat):
        return {
            "station_list": {
                "screen_width": 1150,
                "screen_height": 1255,
                "ne_lat": ne_lat,
                "ne_lon": ne_lon,
                "sw_lat": sw_lat,
                "sw_lon": sw_lon,
                "page_size": 10,
                "page_offset": "",
                "sort_by": "distance",
                "reference_lat": (sw_lat + ne_lat) / 2,
                "reference_lon": (sw_lon + ne_lon) / 2,
                "include_map_bound": True,
                "filter": self._filter_for_query(),
                "bound_output": True,
            }
        }

    def start_requests(self):
        query = self._map_query_for_bounding_box(
            ne_lat=43.0,
            ne_lon=-69.6,
            sw_lat=41.0,
            sw_lon=-73.6,
        )

        yield scrapy.http.JsonRequest(
            url="https://mc.chargepoint.com/map-prod/v2?" + json.dumps(query, separators=(',', ':')),
            method="POST",
            callback=self.parse_map_data,
        )

    def parse_map_data(self, response):
        response_data = response.json()["map_data"]

        for summary in response_data.get("blobs"):
            port_count = sum(list(summary.get("port_count", {}).values()))
            bounds = summary["bounds"]

            if port_count < 100:
                # If there's a small-ish number of ports in this summary bounding box
                # then request station list for the bbox

                # If there's a single station here, the bounding box will have zero area
                # around the point, and the API doesn't like that. So we make it a little
                # bigger manually.
                if bounds["ne_lon"] - bounds["sw_lon"] < 0.001:
                    bounds["ne_lon"] += 0.01
                    bounds["sw_lon"] -= 0.01
                if bounds["ne_lat"] - bounds["sw_lat"] < 0.001:
                    bounds["ne_lat"] += 0.01
                    bounds["sw_lat"] -= 0.01

                query = self._station_query_for_bounding_box(bounds["sw_lon"], bounds["sw_lat"], bounds["ne_lon"], bounds["ne_lat"])

                yield scrapy.http.JsonRequest(
                    url="https://mc.chargepoint.com/map-prod/v2?"
                    + json.dumps(query, separators=(',', ':')),
                    method="POST",
                    callback=self.parse_station_list,
                )
            else:
                # Otherwise make another map data request for the summary bounding box, simulating zooming in
                query = self._map_query_for_bounding_box(bounds["sw_lon"], bounds["sw_lat"], bounds["ne_lon"], bounds["ne_lat"])

                yield scrapy.http.JsonRequest(
                    url="https://mc.chargepoint.com/map-prod/v2?"
                    + json.dumps(query, separators=(',', ':')),
                    method="POST",
                    callback=self.parse_map_data,
                )

    def parse_station_list(self, response):
        station_list = response.json()["station_list"]

        for station in station_list["stations"]:
            yield scrapy.http.JsonRequest(
                url=f"https://mc.chargepoint.com/map-prod/v3/station/info?deviceId={station["device_id"]}",
                method="GET",
                callback=self.parse_device_info,
            )

    def parse_device_info(self, response):
        data = response.json()

        if data.get("address", {}).get("state") != "Massachusetts":
            return

        if data["network"]["name"] == "ChargePoint Network":
            yield from self.parse_device_chargepoint(data)
        else:
            print(data)
            raise

    def parse_device_chargepoint(self, data):
        station_name = " ".join(data["name"])

        location = LocationFeature(**{
            "latitude": data["latitude"],
            "longitude": data["longitude"],
        })
        address = AddressFeature(**{
            "city": data.get("address", {}).get("city"),
            "state": MAPPER_STATE_ABBR_LONG_TO_SHORT.get(data.get("address", {}).get("state")),
            "street_address": data.get("address", {}).get("address1"),
        })

        evses = []

        for port in data["portsInfo"]["ports"]:
            plugs = []

            max_output = port["powerRange"]["max"]
            port_power = PowerFeature(
                output=int(float(max_output) * 1000)
            )

            for connector in port["connectorList"]:
                plug_type = connector["plugType"]

                if plug_type not in self.CONNECTOR_TYPE_TO_PLUG_TYPE_MAP:
                    plug_type = connector["displayPlugType"]

                plug = ChargingPortFeature(
                    plug=self.CONNECTOR_TYPE_TO_PLUG_TYPE_MAP[plug_type],
                    power=port_power,
                )

                plugs.append(plug)

            evse = EvseFeature(
                network_id=f"US*CPI*E{data["deviceId"]}*{port["outletNumber"]}",
                plugs=plugs,
            )
            evses.append(evse)

        charging_point = ChargingPointFeature(
            name=station_name,
            location=location,
            network_id=f"US*CPI*E{data["deviceId"]}",
            evses=evses,
            hardware=HardwareFeature(
                manufacturer="CHARGEPOINT",
                model=data["modelNumber"],
            )
        )

        properties = {
            "network": "CHARGEPOINT",
            "network_id": f"US*CPI*L{data["deviceId"]}",
            "name": station_name,
            "address": address,
            "location": location,
            "charging_points": [charging_point],
            "source": SourceFeature(
                quality="ORIGINAL",
                system="CHARGEPOINT_MAP_V3",
            ),
        }

        yield StationFeature(**properties)

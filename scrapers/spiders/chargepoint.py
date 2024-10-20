from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, LocationFeature, StationFeature

import scrapy

import json
import urllib


class ChargePointSpider(scrapy.Spider):
    name = "chargepoint"

    CONNECTOR_TYPE_TO_PLUG_TYPE_MAP = {
        "J1772": "J1772",
        "CCS1": "J1772_COMBO",
        "CHAdeMO": "CHADEMO",
        "NACS": "NACS",
        "SAE-Combo-CCS1": "J1772_COMBO",

        "NEMA": None,
    }

    def _query_for_bounding_box(self, query_type, sw_lon, sw_lat, ne_lon, ne_lat):
        return {
            query_type: {
                "screen_width": 1024,
                "screen_height": 1024,
                "sw_lon": sw_lon,
                "sw_lat": sw_lat,
                "ne_lon": ne_lon,
                "ne_lat": ne_lat,
                "filter": {
                    "connector_l1": False,
                    "connector_l2": False,
                    "is_bmw_dc_program": False,
                    "is_nctc_program": False,
                    "connector_chademo": False,
                    "connector_combo": False,
                    "connector_tesla": False,
                    "price_free": False,
                    "status_available": False,
                    "network_chargepoint": True,
                    "network_blink": False,
                    "network_semacharge": False,
                    "network_evgo": False,
                    "connector_l2_nema_1450": False,
                    "connector_l2_tesla": False,
                },
            }
        }

    def start_requests(self):
        query = self._query_for_bounding_box(
            "map_data",
            ne_lat=43.0,
            ne_lon=-69.6,
            sw_lat=41.0,
            sw_lon=-73.6,
        )

        yield scrapy.http.JsonRequest(
            url="https://mc.chargepoint.com/map-prod/get?" + urllib.parse.quote(json.dumps(query).encode("utf8")),
            method="GET",
        )

    def parse(self, response):
        response_data = response.json()["map_data"]

        for summary in response_data.get("summaries"):
            port_count = summary.get("port_count", {}).get("total", 0)

            if port_count < 100:
                # If there's a small-ish number of ports in this summary bounding box
                # then request station list for the bbox

                # If there's a single station here, the bounding box will have zero area
                # around the point, and the API doesn't like that. So we make it a little
                # bigger manually.
                if summary["ne_lon"] - summary["sw_lon"] < 0.001:
                    summary["ne_lon"] += 0.01
                    summary["sw_lon"] -= 0.01
                if summary["ne_lat"] - summary["sw_lat"] < 0.001:
                    summary["ne_lat"] += 0.01
                    summary["sw_lat"] -= 0.01

                query = self._query_for_bounding_box("station_list", summary["sw_lon"], summary["sw_lat"], summary["ne_lon"], summary["ne_lat"])

                yield scrapy.http.JsonRequest(
                    url="https://mc.chargepoint.com/map-prod/get?"
                    + urllib.parse.quote(json.dumps(query).encode("utf8")),
                    method="GET",
                    callback=self.parse_station_list,
                )

            else:
                # Otherwise make another map data request for the summary bounding box, simulating zooming in
                query = self._query_for_bounding_box("map_data", summary["sw_lon"], summary["sw_lat"], summary["ne_lon"], summary["ne_lat"])

                yield scrapy.http.JsonRequest(
                    url="https://mc.chargepoint.com/map-prod/get?"
                    + urllib.parse.quote(json.dumps(query).encode("utf8")),
                    method="GET",
                )

    def parse_station_list(self, response):
        station_list = response.json()["station_list"]

        PORT_TYPE_TO_PLUG_TYPE_MAP = {}

        for port_type_id, port_details in station_list.get("port_type_info", {}).items():
            PORT_TYPE_TO_PLUG_TYPE_MAP[int(port_type_id)] = self.CONNECTOR_TYPE_TO_PLUG_TYPE_MAP[port_details["name"]]

        for summary in station_list.get("summaries"):
            station_name = " ".join(summary.get("station_name", [])) or None

            location = LocationFeature(**{
                "latitude": summary["lat"],
                "longitude": summary["lon"],
            })
            address = AddressFeature(**{
                "city": summary.get("address", {}).get("city"),
                "state": summary.get("address", {}).get("state_name"),
                "street_address": summary.get("address", {}).get("address1"),
            })

            evses = []

            for key, outlet in summary["port_status"].items():
                plugs = []

                plug_types = [key for key in outlet.keys() if key.startswith("plug_type")]

                if not plug_types:
                    plug = ChargingPortFeature(**{
                        "plug": PORT_TYPE_TO_PLUG_TYPE_MAP[outlet["port_type"]],
                    })
                    plugs.append(plug)
                else:
                    for plug_type in plug_types:
                        plug = ChargingPortFeature(**{
                            "plug": PORT_TYPE_TO_PLUG_TYPE_MAP[outlet[plug_type]["port_type"]],
                        })
                        plugs.append(plug)

                evse = EvseFeature(
                    network_id=f"US*CPI*E{summary["device_id"]}*{key[7:]}",
                    plugs=plugs,
                )
                evses.append(evse)

            charging_point = ChargingPointFeature(**{
                "name": station_name,
                "location": location,
                "evses": evses,
            })

            properties = {
                "network_id": f"US*CPI*L{summary["device_id"]}",
                "name": station_name,
                "address": address,
                "location": location,
                "charging_points": [charging_point],
            }

            yield StationFeature(**properties)

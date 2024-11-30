from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

from pyzipcode import ZipCodeDatabase
import scrapy

import urllib.parse


zip_search = ZipCodeDatabase()


class AmpupSpider(scrapy.Spider):
    name = "ampup"

    PREFIX_TO_MANUFACTURER_MAP = {
        "juicebar": "JUICE_BAR",
        "evse-llc": "EVSE_LLC",
        "joint-tech": "XIAMEN_JOINT_TECH",
        "dataram": None,
        "powercharge": "POWER_CHARGE",
        "autel": "AUTEL",
        "btc-power": "BTC_POWER",
        "atompower": "ATOM_POWER",
        "ampup-test": None,
        "abb": "ABB",
        "phihong": "PHIHONG",
        "evbox": "EV_BOX",
        "longhorn": "LONGHORN_INTELLIGENT_TECH",
        "ledvance": "LEDVANCE",
    }

    def _query_for_station_list(self, lat_min, lat_max, lng_min, lng_max, zoom):
        return {
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lng_min": lng_min,
            "lng_max": lng_max,
            "networks": "37",
            "connectors": "3,5,6,7,8",
            "is_ampup_only_filter": 1,
            "is_community_charger": 0,
            "is_show_all": 1,
            "is_public_charger": 0,
            "is_show_online": 1,
            "is_ampup_charger": 0,
            "is_fee_required": 0,
            "is_restricted": 0,
            "is_free_charger": 0,
            "is_reservable": 0,
            "add_evanescent": 1,
            "zoom": zoom,
            "limit": 500,
        }

    def start_requests(self):
        for property in ["is_community_charger", "is_public_charger", "is_show_online", "is_reservable", "is_restricted"]:
            query = self._query_for_station_list(
                lat_min=41.0,
                lat_max=43.0,
                lng_min=-73.6,
                lng_max=-69.6,
                zoom=12,
            )
            query[property] = 1

            yield scrapy.http.JsonRequest(
                url="https://main.ampupapis.com/station/get-station-for-mobile-v2?" + urllib.parse.urlencode(query),
                callback=self.parse_station_list,
                meta={
                    "query": query,
                },
            )

    def parse_station_list(self, response):
        stations = response.json()["data"]

        for station in stations:
            if "group_type" in station and "detail" not in station:
                query = response.meta["query"].copy()
                query["lat_min"] = station["lat_min"]
                query["lat_max"] = station["lat_max"]
                query["lng_min"] = station["lng_min"]
                query["lng_max"] = station["lng_max"]
                query["zoom"] += 1

                yield scrapy.http.JsonRequest(
                    url="https://main.ampupapis.com/station/get-station-for-mobile-v2?" + urllib.parse.urlencode(query),
                    callback=self.parse_station_list,
                    meta={
                        "query": query,
                    },
                )
            elif "detail" in station:
                yield from self.parse_station(station["detail"])
            else:
                yield from self.parse_station(station)

    def parse_station(self, station):
        address_parts = station["place_address"].split(", ")

        if len(address_parts) > 2 and address_parts[-1] != "USA":
            if address_parts[-2] == "USA":
                address_parts.pop()

        if len(address_parts) == 3:
            if address_parts[-1].split()[-1].isdigit():
                address_parts.append("USA")

        if address_parts[-1] == "USA":
            state_zip = address_parts[-2].split(" ")
            address = AddressFeature(
                city=address_parts[-3],
                state=state_zip[0],
                zip_code=state_zip[1],
            )

            if len(address_parts) >= 4:
                address["street_address"] = address_parts[-4]

            if state_zip[0] != "MA":
                return
        elif len(address_parts) > 1 and address_parts[-1][0].isdigit():
            zip_info = zip_search.get(address_parts[-1])

            if zip_info is None:
                return

            state = zip_info.state

            if state != "MA":
                return

            address = AddressFeature(
                state=state,
                zip_code=address_parts[-1],
            )
        else:
            address = None

        coordinates = LocationFeature(
            latitude=station["location"]["coordinates"][1],
            longitude=station["location"]["coordinates"][0],
        )

        charging_points = []

        for charger in station["chargers"]:
            name_parts = charger["name"].split("/")
            charger_name = name_parts[-1]

            charging_point = ChargingPointFeature(
                name=charger_name,
            )

            if len(name_parts) > 2:
                charging_point["hardware"] = HardwareFeature(
                    manufacturer=self.PREFIX_TO_MANUFACTURER_MAP[name_parts[1]],
                )

            charging_points.append(charging_point)

        yield StationFeature(
            name=station["place_name"],
            network="AMP_UP",
            network_id=station["id"],
            address=address,
            location=coordinates,
            charging_points=charging_points,
            source=SourceFeature(
                quality="ORIGINAL",
                system="AMP_UP",
            ),
        )

from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature
from scrapy.utils.project import get_project_settings

from pyzipcode import ZipCodeDatabase
import reverse_geocode
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

    PLUG_NAME_TO_TYPE = {
        "J1772": "J1772_CABLE",
        "SAE CCS Combo": "J1772_COMBO",

        "Nema 515": None,
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
        settings = get_project_settings()

        yield scrapy.http.JsonRequest(
            url=f"https://securetoken.googleapis.com/v1/token?key={settings.get("AMP_UP_WEB_API_KEY")}",
            data={
                "grant_type": "refresh_token",
                "refresh_token": settings.get("AMP_UP_REFRESH_TOKEN"),
            },
            callback=self.parse_refresh_token,
        )

    def parse_refresh_token(self, response):
        access_token = response.json()["access_token"]

        for property_name in ["is_community_charger", "is_public_charger", "is_show_online", "is_reservable", "is_restricted"]:
            query = self._query_for_station_list(
                lat_min=41.0,
                lat_max=43.0,
                lng_min=-73.6,
                lng_max=-69.6,
                zoom=12,
            )
            query[property_name] = 1

            yield scrapy.http.JsonRequest(
                url="https://main.ampupapis.com/station/get-station-for-mobile-v2?" + urllib.parse.urlencode(query),
                callback=self.parse_station_list,
                meta={
                    "access_token": access_token,
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
                query["zoom"] += 3

                if station["total"] <= 1 and not self.is_valid_to_retrieve(station["lat_min"], station["lng_min"]):
                    continue
                elif station["total"] < 5:
                    query["zoom"] = max(query["zoom"], 16)

                yield scrapy.http.JsonRequest(
                    url="https://main.ampupapis.com/station/get-station-for-mobile-v2?" + urllib.parse.urlencode(query),
                    callback=self.parse_station_list,
                    meta={
                        "access_token": response.meta["access_token"],
                        "query": query,
                    },
                )
            elif "detail" in station:
                yield from self.parse_station_detail(station["detail"], response)
            else:
                yield from self.parse_station_detail(station, response)

    def is_valid_to_retrieve(self, latitude, longitude) -> bool:
        geocode_data = reverse_geocode.get((latitude, longitude))

        if geocode_data["country_code"] != "US":
            return False

        if "state" in geocode_data and geocode_data["state"] != "Massachusetts":
            return False

        return True

    def parse_station_detail(self, station, response):
        if not self.is_valid_to_retrieve(station["location"]["coordinates"][1], station["location"]["coordinates"][0]):
            return

        yield scrapy.http.JsonRequest(
            url=f"https://main.ampupapis.com/places/{station["id"]}?is_public=false",
            headers={
                "Authorization": f"Bearer {response.meta["access_token"]}",
            },
            meta={
                "station_detail": station,
            },
            callback=self.parse_place,
        )

    def parse_address(self, full_address):
        address_parts = full_address.split(", ")

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

            return address
        elif len(address_parts) > 1 and address_parts[-1][0].isdigit():
            zip_info = zip_search.get(address_parts[-1])

            if zip_info is not None:
                state = zip_info.state

                return AddressFeature(
                    state=state,
                    zip_code=address_parts[-1],
                )

        return None

    def parse_hardware_from_model_id(self, hardware_id):
        HARDWARE_ID_MAP = {
            "5f76d654469b480011b4e123": HardwareFeature(
                manufacturer="EVSE_LLC",
                model="3704",
            ),
            "61c57e4e9079ca4910950a2a": HardwareFeature(
                manufacturer="EVSE_LLC",
                model="3704",
            ),
            "61c57e4d9079ca4910950a27": HardwareFeature(
                manufacturer="EVSE_LLC",
                model="3707",
            ),

            "61c57e479079ca4910950a17": HardwareFeature(
                manufacturer="JUICE_BAR",
                model="320 Series",
            ),
            "61c57e499079ca4910950a1b": HardwareFeature(
                manufacturer="JUICE_BAR",
                model="320 Series",
            ),
            "5f690e36cef1ae001938c9ac": HardwareFeature(
                manufacturer="JUICE_BAR",
                model="400 Series",
            ),
            "5f6389383c4784001100dbe2": HardwareFeature(
                manufacturer="JUICE_BAR",
                model="Mini Bar Single",
            ),

            "cl65xjbm716890i9n944qp0w1": HardwareFeature(
                manufacturer="XIAMEN_JOINT_TECH",
                model="EVC10",
            ),
            "cl65xjpli17970i8id4oyhsla": HardwareFeature(
                manufacturer="XIAMEN_JOINT_TECH",
                model="EVC11",
            ),
        }

        return HARDWARE_ID_MAP.get(hardware_id)

    def parse_station(self, station):
        address = self.parse_address(station["place_address"])

        if address is None or address["state"] != "MA":
            return

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

    def parse_place(self, response):
        if "data" not in response.json():
            yield from self.parse_station(response.meta["station_detail"])

            return

        station = response.json()["data"]

        address = self.parse_address(station["place_address_full"])

        if address is not None and address["state"] != "MA":
            return

        coordinates = LocationFeature(
            latitude=station["lat"],
            longitude=station["lng"],
        )

        charging_points = []

        for charger in station["chargers"]:
            name_parts = charger["name"].split("/")
            charger_name = name_parts[-1]

            evses = []

            for plug in charger["plugs"]:
                evses.append(
                    EvseFeature(
                        plugs=[
                            ChargingPortFeature(
                                plug=self.PLUG_NAME_TO_TYPE[plug["name"]],
                                power=PowerFeature(
                                    output=int(plug["power"] * 1000),
                                ),
                            ),
                        ],
                        network_id=plug["outlet_id"],
                    )
                )

            if len(charger["plugs"]) == 1:
                charger_name = charger["plugs"][0]["qr_id"]

            charging_point = ChargingPointFeature(
                name=charger_name,
                evses=evses,
                network_id=charger["id"],
            )

            if hardware := self.parse_hardware_from_model_id(charger["modelId"]):
                charging_point["hardware"] = hardware
            elif len(name_parts) > 2:
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

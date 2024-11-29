from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

from pyzipcode import ZipCodeDatabase
import rsa
import scrapy

from urllib.parse import urlencode
import base64
import json


zip_search = ZipCodeDatabase()


class EnelXSpider(scrapy.Spider):
    name = "enelx"

    handle_httpstatus_list = [200, 401]

    AUTH_HEADERS = {
        "Authorization": "Basic YXBwLWVnbzp5dnI0bjZ3MWM0eHpsZnNn",
        "userid": "guest@guest.com",
    }

    TYPOLOGY_TO_PLUG_TYPE = {
        "CHADEMO": "CHADEMO",
        "CCS1": "J1772_COMBO",
        "TYPE_1": "J1772_CABLE",
    }

    def _get_query_params(self, ne_lat, ne_lon, sw_lat, sw_lon, zoom):
        return {
            "zoomLevel": zoom,
            "lat": (ne_lat + sw_lat) / 2,
            "lon": (ne_lon + sw_lon) / 2,
            "isPrivate": "false",
            "swLat": sw_lat,
            "swLon": sw_lon,
            "neLat": ne_lat,
            "neLon": ne_lon,
        }

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://emobility-us.enelx.com/api/authentication/v1/oauth/key",
            headers=self.AUTH_HEADERS,
            callback=self.parse_public_key,
        )

    def parse_public_key(self, response):
        response_data = response.json()["result"]

        id_session = response_data["idSession"]

        pem = "-----BEGIN PUBLIC KEY-----\n" + response_data["publicKey"] + "\n-----END PUBLIC KEY-----\n"
        public_key = rsa.PublicKey.load_pkcs1_openssl_pem(pem)

        salted_password = id_session + ":guest"

        raw_password = rsa.encrypt(salted_password.encode("ascii"), public_key)

        password = base64.b64encode(raw_password).decode("ascii")

        yield scrapy.http.JsonRequest(
            url="https://emobility-us.enelx.com/api/authentication/v3/oauth/login",
            method="POST",
            data={
                "encrypted": True,
                "idSession": id_session,
                "fields": [
                    "password",
                ],
                "bodyOfMessage": json.dumps({
                    "email": "guest@guest.com",
                    "password": password,
                })
            },
            headers=self.AUTH_HEADERS,
            callback=self.parse_oauth_login,
        )

    def parse_oauth_login(self, response):
        auth_data = response.json()["result"]

        params = self._get_query_params(
            ne_lat=43.0,
            ne_lon=-69.6,
            sw_lat=41.0,
            sw_lon=-73.6,
            zoom=8,
        )

        yield scrapy.http.JsonRequest(
            url="https://emobility-us.enelx.com/api/emobility/v2/charging/station?" + urlencode(params),
            headers={
                "authorization": f"Bearer {auth_data["access_token"]}",
            },
            meta={
                "query": params,
                "auth": auth_data
            },
            callback=self.parse_station_list,
        )

    def parse_station_list(self, response):
        clusters = response.json()["result"]

        for cluster in clusters:
            if cluster["num"] == 1:
                auth_data = response.meta["auth"]

                if "CPI" in cluster["serialNumber"]:
                    continue

                yield scrapy.http.JsonRequest(
                    url=f"https://emobility-us.enelx.com/api/emobility/asset/v2/charging-station/sn/{cluster["serialNumber"]}",
                    headers={
                        "authorization": f"Bearer {auth_data["access_token"]}",
                    },
                    meta={
                        "auth": auth_data
                    },
                    callback=self.parse_station,
                )
            elif response.meta["query"]["zoomLevel"] < 10:
                prev_params = response.meta["query"]
                auth_data = response.meta["auth"]

                buffer = cluster["num"] * 0.05

                params = self._get_query_params(
                    zoom=prev_params["zoomLevel"] + 1,
                    ne_lat=cluster["lat"] + buffer,
                    ne_lon=cluster["lon"] + buffer,
                    sw_lat=cluster["lat"] - buffer,
                    sw_lon=cluster["lon"] - buffer,
                )

                yield scrapy.http.JsonRequest(
                    url="https://emobility-us.enelx.com/api/emobility/v2/charging/station?" + urlencode(params),
                    headers={
                        "authorization": f"Bearer {auth_data["access_token"]}",
                    },
                    meta={
                        "query": params,
                        "auth": auth_data
                    },
                    callback=self.parse_station_list,
                )

    def parse_station(self, response):
        data = response.json()["result"]

        station = self.parse_station_base(data)

        if station["address"]["state"] != "MA":
            return

        if data["managed"] == "OCPI_WORKFORCE":
            station["source"] = SourceFeature(
                system="ENEL_X_EMOBILITY_US",
                quality="PARTNER",
            )

            if data["tenantId"] in ["CPI_US_OCPI"]:
                station = self.parse_station_chargepoint(data, station)
            else:
                raise
        else:
            station["source"] = SourceFeature(
                system="ENEL_X_EMOBILITY_US",
                quality="ORIGINAL",
            )

            station = self.parse_station_enel_x(data, station)

        station["charging_points"] = self.parse_charging_points(data)

        yield station

    def parse_station_base(self, data):
        coordinates = LocationFeature(
            latitude=data["csGeoLat"],
            longitude=data["csGeoLon"],
        )

        street_address = data["address"]
        if ", " in data["address"]:
            address_parts = data["address"].rsplit(", ", 1)

            if address_parts[1].isdigit():
                street_address = f"{address_parts[1]} {address_parts[0]}"

        zip_info = zip_search.get(data["postalcode"])
        state = zip_info.state

        city = data["city"]

        if city == "NA":
            city = zip_info.city

        address = AddressFeature(
            street_address=street_address,
            city=city,
            state=state,
            zip_code=data["postalcode"],
        )

        return StationFeature(
            name=data["csName"],
            location=coordinates,
            address=address,
        )

    def _normalize_ocpi_id(self, ocpi_id, type_override=None):
        if ocpi_id[2] == "*":
            return ocpi_id

        ocpi_id = self._ocpi_serial_number_to_network_id(ocpi_id)

        if type_override:
            ocpi_id = f"{ocpi_id[:7]}{type_override}{ocpi_id[8:]}"

        return ocpi_id

    def _ocpi_serial_number_to_network_id(self, serial_number):
        country_code = serial_number[0:2]
        cpo_code = serial_number[2:5]
        type = serial_number[5]
        identifier = serial_number[6:]

        return f"{country_code}*{cpo_code}*{type}{identifier}"

    def parse_station_chargepoint(self, data, station):
        station["network"] = "CHARGEPOINT"
        station["network_id"] = self._normalize_ocpi_id(data["serialNumber"], "L")

        return station

    def parse_station_enel_x(self, data, station):
        station["network"] = "ENEL_X"

        evse_id = data["evses"][0]["evseId"]
        cpo_id = evse_id[3:6]

        station["network_id"] = f"{data["country"]}*{cpo_id}*L{data["serialNumber"]}"

        return station

    def parse_charging_points(self, data):
        evses = []

        for evse in data["evses"]:
            plugs = []

            for plug in evse["plugs"]:
                plugs.append(
                    ChargingPortFeature(
                        plug=self.TYPOLOGY_TO_PLUG_TYPE[plug["typology"]],
                        power=PowerFeature(
                            amperage=plug["maxCurrent"],
                            output=int(plug["maxPower"] * 1000),
                        )
                    )
                )

            evses.append(
                EvseFeature(
                    plugs=plugs,
                    network_id=self._normalize_ocpi_id(evse["evseId"]),
                )
            )

        charging_point = ChargingPointFeature(
            name=data["csName"],
            network_id=data["serialNumber"],
            evses=evses,
        )

        return [charging_point]

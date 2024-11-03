from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

from collections import defaultdict

import scrapy


class BlinkSpider(scrapy.Spider):
    name = "blink"

    PLUG_FOR_CONNECTOR_TYPE = {
        "J1772": "J1772",
        "CHAdeMO": "CHADEMO",
        "CCS1": "J1772_COMBO",
    }

    def _query_for_location(self, lat, lon, radius):
        return {
            "latitude": lat,
            "longitude": lon,
            "latitudeDelta": 0,
            "longitudeDelta": 0,
            "deviceCurrentLat": lat,
            "deviceCurrentLng": lon,
            "radius": radius,
        }

    def start_requests(self):
        query = self._query_for_location(
            lat=42.13,
            lon=-71.76,
            radius=145,
        )

        yield scrapy.http.JsonRequest(
            url="https://apigw.blinknetwork.com/nmap/v3/locations/map/pins",
            data=query,
            method="POST",
        )

    def parse(self, response):
        locations = response.json()

        for location in locations:
            yield scrapy.http.JsonRequest(
                url=f"https://apigw.blinknetwork.com/v3/locations/map/{location["locationId"]}",
                method="GET",
                meta={
                    "location": location,
                },
                callback=self.parse_station,
            )

    def parse_station(self, response):
        station = response.json()

        if station["address"]["countryCode"] != "US":
            return

        if station["address"]["state"] != "Massachusetts":
            return

        yield scrapy.http.JsonRequest(
            url=f"https://apigw.blinknetwork.com/v3/locations/{station["locationId"]}?isPrivateStationReq=false",
            method="GET",
            meta={
                "station": station,
                "location": response.meta["location"],
            },
            callback=self.parse_chargers,
        )

    def parse_chargers(self, response):
        response_data = response.json()
        station = response.meta["station"]
        location = response.meta["location"]

        address = AddressFeature(
            street_address=station["address"]["addressLine1"],
            city=station["address"]["city"],
            state=station["address"]["state"],
            zip_code=station["address"]["postalCode"],
        )

        coordinates = LocationFeature(
            latitude=location["latitude"],
            longitude=location["longitude"],
        )

        charging_points = []

        charging_point_serials = {}
        ports_for_charging_points = defaultdict(list)

        for charger_class in response_data:
            for charger in charger_class["chargers"]:
                if charger["serialNumber"] not in charging_point_serials:
                    charging_point_serials[charger["serialNumber"]] = ChargingPointFeature(
                        location=coordinates,
                        network_id=charger["serialNumber"],
                        hardware=self.hardware_for_serial_number(charger["serialNumber"], charger),
                        evses=[],
                    )

                port = ChargingPortFeature(
                    plug=self.PLUG_FOR_CONNECTOR_TYPE[charger["connectorType"]],
                    power=PowerFeature(
                        voltage=int(charger["maxVoltage"]),
                        amperage=int(charger["maxCurrent"]),
                        output=int(charger["maxPower"]),
                    ),
                )
                evse = EvseFeature(
                    plugs=[port],
                    network_id=charger["portId"],
                )

                ports_for_charging_points[charger["serialNumber"]].append(evse)

        for charging_serial, evses in ports_for_charging_points.items():
            charging_point = charging_point_serials[charging_serial]
            charging_point["evses"] = evses

        for charging_point in charging_point_serials.values():
            charging_points.append(charging_point)

        yield StationFeature(
            name=station["locationName"],
            network="BLINK",
            network_id=station["locationId"],
            address=address,
            location=coordinates,
            charging_points=charging_points,
            source=SourceFeature(
                quality="ORIGINAL",
                system="BLINK",
            ),
        )

    def hardware_for_serial_number(self, serial_number, charger):
        brand = "BLINK"
        manufacturer = None
        model = None

        if serial_number.startswith("BAE"):
            brand = "SEMA_CONNECT"
            manufacturer = "SEMA_CONNECT"

            model_number = serial_number[3:7]

            if model_number[0] == "0":
                model_number = model_number[1:]
            else:
                model_number = model_number[:3]

            if model_number.startswith("6") or model_number.startswith("9"):
                model = "Series 6"

                if model_number in [
                    "601", "901",
                    "602", "902",
                    "603", "903",
                ]:
                    brand = "CHARGEPRO"
            elif model_number.startswith("7"):
                model = "Series 7"
            elif model_number.startswith("8"):
                model = "Series 8"
            else:
                raise Exception(charger)
        elif serial_number.startswith("L1-") or serial_number.startswith("L2-"):
            manufacturer = "BLINK"

            model_number = int(serial_number.split("-")[1])

            model_map = {
                202: "MQ 200",
                203: "MQ 200",
                205: "HQ 200",
                207: "IQ 200",
            }

            if model_number in model_map:
                model = model_map[model_number]
            else:
                raise Exception(charger)
        elif serial_number.startswith("CTX") or serial_number.startswith("2022"):
            manufacturer = "TELLUS_POWER_GREEN"
            model = f"TP5-{int(charger["maxPower"] / 1000)}-480"
        elif serial_number.startswith("NAMT53"):
            manufacturer = "ABB"
            model = "Terra 53"
        elif serial_number.startswith("1210"):
            manufacturer = "TRITIUM"
            model = "RT50"
        elif serial_number.startswith("3221"):
            manufacturer = "TRITIUM"
            model = "RT175-S"
        elif serial_number[0].isdigit():
            raise Exception(charger)
        else:
            raise Exception(charger)

        return HardwareFeature(
            brand=brand,
            manufacturer=manufacturer,
            model=model,
        )

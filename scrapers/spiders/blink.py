# Wallingford, CT       Executive Honda                 MQ 200                  L1-0202-2245-001703
# Greenwich, CT         West Putnam Owner               MQ 200                  L1-0203-2225-000554
# Ludlow, VT            Main & Mountain                 HQ 200                  L1-0205-W-2233-003986
# Bedford, MA           Depot Park                      IQ 200                  L1-0207-2005-002228, L1-0207-2028-003958
# Westwood, MA          Audi Westwood                   IQ 200                  L1-0207-LTE-W-2217-008565
# Norwell, MA           Audi Norwell                    IQ 200                  L1-0207-ISO-2240-012518, L1-0207-ISO-2240-012465
# Fall River, MA        Burger King                     IQ 200                  L1-0207-2019-003581
# Enfield, CT           AAA Enfield                     IQ 200                  L1-0207-LTE-W-2148-006747
# Mansfield, MA         5 Hampshire Street              Series 6 (SemaConnect)  BAE909384
# Granby, CT            Grande Luxury Apartments        Series 6 (SemaConnect)  BAE907691
# Hyannis, MA           Hyannis Main Street             Series 6 (SemaConnect)  BAE906774
# Wellfleet, MA         Welfleet Town Hall              Series 6 (SemaConnect)  BAE607387, BAE607391
# Edgartown, MA         Winnetu Oceanside Resort        Series 6 (SemaConnect)  BAE911113, BAE911114
# East Hampton, CT      Airline Trail Parking Lot       Series 6 (SemaConnect)  BAE905534
# New Haven, CT         Grove St Parking Lot            Series 6 (SemaConnect)  BAE908259, BAE908260
# Fairfield, CT         Alto Fairfield Metro            Series 6 (SemaConnect)  BAE912208
# Westport, CT          Staples High School             Series 6 (SemaConnect)  BAE904592, BAE905405
# Manchester Center, VT Northshire Bookstore            Series 6 (SemaConnect)  BAE904834
# Middlebury, VT        Marble Works Partnership        Series 6 (SemaConnect)  BAE902916, BAE902140
# Bloomfield, CT        Bloomfield Town Hall            Series 6 (ChargePro)    BAE060043, BAE902440
# Bloomfield, CT        Bloomfield Human Servies        Series 6 (ChargePro     BAE609624, BAE903620
# Watrerford, CT        Henny Penny                     Series 6 (ChargePro)    BAE901741, BAE901742
# Bridgeport, CT        Steele Harbor                   Series 6 (ChargePro)    BAE903263
# White Plains, NY      City Square Parking             Series 6 (ChargePro)    BAE903878, BAE603146
# Manchester Center, VT Northshite Bookstore            Series 6 (ChargePro)    BAE901281
# Lynn, MA              Lynn Ferry Terminal             Series 7                BAE712606, BAE712612
# Windsor, CT           Travelers Claim University      Series 7                BAE070017, BAE701944, BAE701949
# Bedford, MA           Bedford Campus                  Series 8                BAE800221, BAE800222
# Norwell, MA           Audi Norwell                    TP5-30-480              20220460913
# Fair Haven, VT        Town of Fair Haven              TP5-60-480              CTX24010072, CTX24010076
# Littleton, MA         Littleton Power Department      TP5-120-480             CTX23010176
# Westwood, MA          Westwood Police Department      TP5-120-480             CTX23101305
# East Hartford, CT     Gengras Chrysler Dodge Jeep     TP5-180-480             CTX23070908
# Springfield, VT       Irving Oil                      RT175-S                 322100032, 322100033
# Wilmington, VT        Town of Wilmington              RT50                    12100261, 12100262
# Ludlow, VT            Main & Mountain                 RT50                    12100265, 12100267
# Budd Lake, NJ         Holiday Inn - Budd Lake         ABB Terra 54?           NAMT53-2415-033

from collections import defaultdict
from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, StationFeature

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
        elif serial_number.startswith("CTX"):
            manufacturer = "TELLUS_POWER_GREEN"
            model = f"TP5-{int(charger["maxPower"] / 1000)}-480"
        elif serial_number.startswith("NAMT53"):
            manufacturer = "ABB"
            model = "Terra 53"
        else:
            raise Exception(charger)

        return HardwareFeature(
            brand=brand,
            manufacturer=manufacturer,
            model=model,
        )

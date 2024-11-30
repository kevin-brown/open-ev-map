from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

from websockets.asyncio.client import connect
import scrapy

import json
import uuid


class ChargeLabSpider(scrapy.Spider):
    name = "chargelab"

    app_id = "co.chargelab"
    app_version = "3.14.0"

    start_urls = ["data:text/plain,noop", ]

    NETWORK_MAP = {
        None: "CHARGE_LAB",
        "CHARGELAB": "CHARGE_LAB",
        "EATON": "EATON",
        "TURNONGREEN": "TURN_ON_GREEN",
    }

    CONNECTOR_TO_PLUG = {
        "J1772": "J1772_CABLE",
    }

    async def parse(self, _):
        session_id = str(uuid.uuid4())

        async with connect(f"wss://api.chargelab.co/charge?{session_id}", max_size=None) as ws:
            connect_headers = {
                "Access-Control-Allow-Origin": "*",
                "Authorization": f"Bearer {session_id}",
                "accept-version": "1.2",
                "heart-beat": "1000,1000",
            }

            await ws.send(self.stomp_encode("CONNECT", headers=connect_headers))

            message = await ws.recv()

            general_subscribe_headers = {
                "destination": "/topic/v2/cp",
                "id": "sub-0",
            }

            await ws.send(self.stomp_encode("SUBSCRIBE", headers=general_subscribe_headers))

            secured_subscribe_headers = {
                "destination": f"/topic/v2/secured/{session_id}",
                "id": "sub-1",
            }

            await ws.send(self.stomp_encode("SUBSCRIBE", headers=secured_subscribe_headers))

            locations_headers = {
                "event": "V2_LOCATIONS",
                "destination": "/app/cp/v2",
            }

            location_request = {
                "eventType": "V2_LOCATIONS",
                "requestId": str(uuid.uuid4()),
                "searchParam": "",
                "chargePointsDistanceRequest": {
                    "latitude": 42.13,
                    "longitude": -71.76,
                    "distance": -1,
                },
                "filters": [],
                "appInfo": {
                    "appId": self.app_id,
                    "appVersion": self.app_version,
                    "appSelectedLanguage": "en",
                },
                "session": session_id,
            }

            await ws.send(self.stomp_encode("SEND", headers=locations_headers, body=json.dumps(location_request)))

            wait_for_message = True

            while wait_for_message:
                message = await ws.recv()

                command, headers, body = self.stomp_decode(message)

                if command != "MESSAGE":
                    continue

                if headers["subscription"] == "sub-1" and headers["event"] == "V2_LOCATIONS":
                    async for location in self.parse_locations(body):
                        yield location

                    wait_for_message = False

            await ws.close()

    async def parse_locations(self, data):
        location_dtos = data["locationWithDistanceDtos"]

        for location_dto in location_dtos:
            location = location_dto["locationDto"]

            site_network_id = None

            if location["address"]["province"] != "MA":
                continue

            location_address = location["address"]

            address = AddressFeature(
                street_address=f"{location_address["houseNumber"]} {location_address["street"]}",
                city=location_address["city"],
                state=location_address["province"],
                zip_code=location_address["zipCode"],
            )

            coordinates = LocationFeature(
                latitude=location["latitude"],
                longitude=location["longitude"],
            )

            charging_points = []

            for charge_point_type in location["chargePointTypeDtos"]:
                for charge_point in charge_point_type["chargePointShortDtos"]:
                    charge_point_coordinates = LocationFeature(
                        latitude=charge_point["latitude"],
                        longitude=charge_point["longitude"],
                    )

                    if charge_point["whiteLabelNetworkId"]:
                        site_network_id = charge_point["whiteLabelNetworkId"]

                    power_amt, power_units = charge_point["maxPower"].split()

                    if power_units == 'kW':
                        power_output = int(float(power_amt) * 1000)

                    evses = []

                    for connector in charge_point["connectorDtoList"]:
                        evses.append(
                            EvseFeature(
                                plugs=[
                                    ChargingPortFeature(
                                        plug=self.CONNECTOR_TO_PLUG[connector["connectorType"]],
                                        power=PowerFeature(
                                            output=power_output,
                                        ),
                                    )
                                ],
                                network_id=connector["connectorId"],
                            )
                        )

                    charging_points.append(
                        ChargingPointFeature(
                            name=charge_point["stationId"],
                            network_id=charge_point["id"],
                            location=charge_point_coordinates,
                            evses=evses,
                        )
                    )

            yield StationFeature(
                name=location["name"],
                network=self.NETWORK_MAP[site_network_id],
                network_id=location["id"],
                location=coordinates,
                address=address,
                charging_points=charging_points,
                source=SourceFeature(
                    system="CHARGE_LAB",
                    quality="ORIGINAL",
                ),
            )
        
    def stomp_encode(self, command, headers=None, body=None):
        lf = '\x0A'
        null = '\x00'

        lines = [command]

        if headers is None:
            headers = {}

        if body:
            headers["content-length"] = len(body)

        if headers:
            for name, value in headers.items():
                lines.append(f"{name}:{value}")

        lines.append("")

        if body:
            lines.append(body + null)
        else:
            lines.append(null)

        return lf.join(lines)

    def stomp_decode(self, message):
        lines = message.decode("utf-8").split("\x0A")

        command = lines[0]
        header_lines = lines[1:-2]
        headers = {}
        body_line = lines[-1][:-1]

        for line in header_lines:
            name, value = line.split(":", 1)
            headers[name] = value

        if body_line:
            body = json.loads(body_line)
        else:
            body = None

        return command, headers, body

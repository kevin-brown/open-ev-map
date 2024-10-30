from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, LocationFeature, PowerFeature, StationFeature

import scrapy
import shapely


class FloSpider(scrapy.Spider):
    name = "flo"
    STANDARD_TO_PLUG_TYPE_MAP = {
        "IEC_62196_T1": "J1772_CABLE",
        "IEC_62196_T1_COMBO": "J1772_COMBO",
        "CHADEMO": "CHADEMO",
    }

    def _query_for_bounding_box(self, zoom, sw_lon, sw_lat, ne_lon, ne_lat):
        return {
            "zoomLevel": zoom,
            "bounds": {
                "SouthWest": {
                    "Latitude": sw_lat,
                    "Longitude": sw_lon,
                },
                "NorthEast": {
                    "Latitude": ne_lat,
                    "Longitude": ne_lon,
                },
            },
            "filter": {
                "networkIds": [],
                "connectors": None,
                "levels": [],
                "rates": [],
                "statuses": [],
                "minChargingSpeed": None,
                "maxChargingSpeed": None,
            },
        }

    def start_requests(self):
        query = self._query_for_bounding_box(
            zoom=9,
            ne_lat=43.0,
            ne_lon=-69.6,
            sw_lat=41.0,
            sw_lon=-73.6,
        )

        yield scrapy.http.JsonRequest(
            url="https://emobility.servicesflo.com/v3.0/map/markers/search",
            data=query,
            meta={
                "query": query,
            },
            method="POST",
        )

    def parse(self, response):
        response_data = response.json()

        print(response_data)
        print(response.meta)

        if response_data["parks"]:
            yield from self.parse_parks(response)

        if response_data["clusters"]:
            yield from self.parse_clusters(response)

    def parse_clusters(self, response):
        response_data = response.json()
        original_query = response.meta["query"]
        bounds = original_query["bounds"]

        width = bounds["NorthEast"]["Latitude"] - bounds["SouthWest"]["Latitude"]
        height = bounds["NorthEast"]["Longitude"] - bounds["SouthWest"]["Longitude"]

        quadrants = (
            {
                "ne_lat": bounds["NorthEast"]["Latitude"],
                "ne_lon": bounds["NorthEast"]["Longitude"],
                "sw_lat": bounds["NorthEast"]["Latitude"] + width / 2,
                "sw_lon": bounds["NorthEast"]["Longitude"] + height / 2,
            },
            {
                "ne_lat": bounds["NorthEast"]["Latitude"] + width / 2,
                "ne_lon": bounds["NorthEast"]["Longitude"] + height / 2,
                "sw_lat": bounds["SouthWest"]["Latitude"],
                "sw_lon": bounds["SouthWest"]["Longitude"],
            },
        )

        for cluster in response_data["clusters"]:
            cluster_point = shapely.Point(cluster["geoCoordinates"]["latitude"], cluster["geoCoordinates"]["longitude"])

            for quadrant in quadrants:
                quadrant_bounds = shapely.box(
                    xmin=quadrant["ne_lat"],
                    xmax=quadrant["sw_lat"],
                    ymin=quadrant["ne_lon"],
                    ymax=quadrant["sw_lon"],
                )

                if shapely.contains(quadrant_bounds, cluster_point):
                    query = self._query_for_bounding_box(
                        zoom=original_query["zoomLevel"] + 1,
                        **quadrant,
                    )

                    yield scrapy.http.JsonRequest(
                        url="https://emobility.servicesflo.com/v3.0/map/markers/search",
                        data=query,
                        meta={
                            "query": query,
                            "shape": {
                                "height": height,
                                "width": width,
                            },
                        },
                        method="POST",
                    )

                    break

    def parse_parks(self, response):
        response_data = response.json()

        for park in response_data["parks"]:
            if park["networkId"] not in [1, 6]:
                continue

            for station in park["stations"]:
                yield scrapy.http.JsonRequest(
                    url=f"https://emobility.servicesflo.com/v3.0/parks/station/{station["id"]}",
                    method="GET",
                    callback=self.parse_station,
                )

    def parse_station(self, response):
        park = response.json()

        address = AddressFeature(
            street_address=park["address"]["address1"],
            city=park["address"]["city"],
            state=park["address"]["province"],
            zip_code=park["address"]["postalCode"],
        )

        location = LocationFeature(**park["geoCoordinates"])

        charging_points = []

        for station in park["stations"]:
            evses = []
            ports = []

            for connector in station["connectors"]:
                power = PowerFeature(
                    output=connector["power"],
                )

                port = ChargingPortFeature(
                    plug=self.STANDARD_TO_PLUG_TYPE_MAP[connector["type"]],
                    power=power,
                )
                ports.append(port)

            evses = [
                EvseFeature(
                    plugs=ports,
                )
            ]

            charging_point = ChargingPointFeature(
                name=station["name"],
                network_id=station["id"],
                evses=evses,
            )
            charging_points.append(charging_point)

        yield StationFeature(
            name=park["name"],
            network="FLO",
            network_id=park["id"],
            address=address,
            location=location,
            charging_points=charging_points,
        )

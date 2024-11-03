from scrapers.items import ChargingPointFeature, StationFeature

import scrapy
import shapely


class OpenstreetmapSpider(scrapy.Spider):
    name = "openstreetmap"

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://overpass-api.de/api/interpreter?data=%5Bout%3Ajson%5D%3B%0Aarea%5Bname%3D%22Massachusetts%22%5D%5Badmin_level%3D4%5D%5Bboundary%3Dadministrative%5D-%3E.mass%3B%0A%28%0A%20%20nwr%28area.mass%29%5Bamenity%3Dcharging_station%5D%3B%0A%20%20nwr%28area.mass%29%5Bman_made%3Dcharge_point%5D%3B%0A%29%3B%0Aout%20geom%3B",
        )

    def parse(self, response):
        elements = response.json()

        stations: dict[int, StationFeature] = {}

        charge_points: dict[int, ChargingPointFeature] = {}
        station_bounds: dict[int, shapely.Polygon] = {}

        for element in elements:
            if element["tags"].get("amenity") != "charging_station":
                continue

            stations[element["id"]] = self.parse_charging_station(element)

            if element["type"] == "way":
                station_bounds[element["id"]] = self.parse_charging_station_bounds(element)

        for element in elements:
            if element["tags"].get("man_made") != "charge_point":
                continue

            charge_point = self.parse_charge_point(element)

            charge_point_associated = False

            for station_id, station_boundary in station_bounds.items():
                if shapely.contains(station_boundary, charge_point.location.get().point):
                    stations[station_id].charging_points.append(charge_point)

                    charge_point_associated = True

                    break

            if not charge_point_associated:
                charge_points[element["id"]] = charge_point

        for element in elements:
            if element["tags"].get("amenity") != "charging_station":
                continue

            if element["type"] != "relation":
                continue

            for member in element["members"]:
                if member["ref"] in charge_points:
                    stations[element["id"]].charging_points.append(charge_points[member["ref"]])
                    del charge_points[member["ref"]]

        charge_points_found = []

        for charge_point_id, charge_point in charge_points.items():
            charge_point_network = charge_point._osm_network

            for station_id, station in stations.items():
                if charge_point_network != station.network:
                    continue

                charge_point_distance_to_station = self.get_station_distance(station, charge_point)

                if charge_point_distance_to_station.miles > 0.05:
                    continue

                station.charging_points.append(charge_point)

                charge_points_found.append(charge_point_id)

                break

        for charge_point_id in charge_points_found:
            del charge_points[charge_point_id]

        yield from stations.values()

    def parse_charging_station_bounds(self, element):
        return shapely.box(
            xmin=element["bounds"]["minlat"],
            xmax=element["bounds"]["maxlat"],
            ymin=element["bounds"]["minlon"],
            ymax=element["bounds"]["maxlon"],
        )

    def get_station_distance(self, station, charging_point):
        pass

    def parse_charging_station(self, element):
        pass

    def parse_charge_point(self, element):
        pass

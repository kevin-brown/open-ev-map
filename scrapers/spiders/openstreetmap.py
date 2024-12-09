from scrapers.items import AddressFeature, ChargingPointFeature, LocationFeature, ReferenceFeature, SourceFeature, StationFeature

from geopy import distance
import scrapy
import shapely


class OpenStreetMapSpider(scrapy.Spider):
    name = "openstreetmap"

    EXCLUDED_NAMES = [
        "evgo",
        "chargepoint",
        "tesla destination charger",
        "tesla supercharger",
        "tesla supercharging station",
    ]

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://overpass-api.de/api/interpreter?data=%5Bout%3Ajson%5D%3B%0Aarea%5Bname%3D%22Massachusetts%22%5D%5Badmin_level%3D4%5D%5Bboundary%3Dadministrative%5D-%3E.mass%3B%0A%28%0A%20%20nwr%28area.mass%29%5Bamenity%3Dcharging_station%5D%3B%0A%20%20nwr%28area.mass%29%5Bman_made%3Dcharge_point%5D%3B%0A%29%3B%0Aout%20geom%3B",
        )

    def parse(self, response):
        elements = response.json()["elements"]

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
                if shapely.contains(station_boundary, charge_point["location"].point()):
                    stations[station_id]["charging_points"].append(charge_point)

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
                    stations[element["id"]]["charging_points"].append(charge_points[member["ref"]])
                    del charge_points[member["ref"]]

        charge_points_found = []

        for charge_point_id, charge_point in charge_points.items():
            charge_point_network = charge_point._osm_network

            for station_id, station in stations.items():
                if charge_point_network != station["network"]:
                    continue

                charge_point_distance_to_station = self.get_station_distance(station, charge_point)

                if charge_point_distance_to_station.miles > 0.05:
                    continue

                station["charging_points"].append(charge_point)

                charge_points_found.append(charge_point_id)

                break

        for charge_point_id in charge_points_found:
            del charge_points[charge_point_id]

        yield from stations.values()

    def parse_charging_station_bounds(self, element) -> shapely.Polygon:
        return shapely.box(
            xmin=element["bounds"]["minlat"],
            xmax=element["bounds"]["maxlat"],
            ymin=element["bounds"]["minlon"],
            ymax=element["bounds"]["maxlon"],
        )

    def get_station_distance(self, station, charging_point):
        first_location = station["location"]
        second_location = charging_point["location"]

        first_coordinates = first_location.coordinates()
        second_coordinates = second_location.coordinates()

        station_distance = distance.great_circle(first_coordinates, second_coordinates)

        return station_distance

    def network_from_osm_tags(self, tags) -> str:
        OSM_NETWORK_NAME_MAP = {
            "AmpUp": "AMP_UP",
            "Autel": "AUTEL",
            "Blink": "BLINK",
            "ChargePoint": "CHARGEPOINT",
            "Electrify America": "ELECTRIFY_AMERICA",
            "Enel X": "ENEL_X",
            "EV Connect": "EV_CONNECT",
            "EVgo": "EVGO",
            "Electric Era": "ELECTRIC_ERA",
            "EVPassport": "EV_PASSPORT",
            "Greenspot": "GREEN_SPOT",
            "Loop": "LOOP",
            "Tesla": None, # Ambiguous
            "Tesla, Inc.": None, # Ambiguous
            "Tesla Supercharger": "TESLA_SUPERCHARGER",
            "Volta": "SHELL_RECHARGE",
        }

        OSM_NETWORK_WIKIDATA_MAP = {
            # Tesla, Inc., currently ambiguous
            "Q478214": None,

            "Q17089620": "TESLA_SUPERCHARGER",
            "Q5176149": "CHARGEPOINT",
            "Q59773555": "ELECTRIFY_AMERICA",
            "Q61803820": "EVGO",
            "Q62065645": "BLINK",
            "Q64971203": "FLO",
            "Q105883058": "SHELL_RECHARGE",
            "Q109307156": "SHELL_RECHARGE", # Volta
            "Q126652985": "EV_CONNECT",
        }

        OSM_OPERATOR_NAME_MAP = {
            "Bread Euphoria": None, # Non-networked
            "City of Melrose": None, # ChargePoint via Brand
            "City of Newton": None, # ChargePoint via Brand
            "National Grid": None, # Non-networked
            "Regus": None,  # Non-networked
            "Town of Bolton": None,
            "Whole Foods": None,
            "Mass Audubon": None,

            "Tesla, Inc.": None, # Ambiguous
            "Tesla Motors": None, # Ambiguous

            "AmpUp": "AMP_UP",
            "ChargePoint": "CHARGEPOINT",
            "Shell Recharge Solutions": "SHELL_RECHARGE",
        }

        OSM_OPERATOR_WIKIDATA_NETWORK_MAP = {
            # ABB Group
            "Q52825": None,
            # Tesla, Inc., currently ambiguous
            "Q478214": None,
            # AeroVironment
            "Q919300": None,
            # NRG Energy, most likely EVgo
            "Q6955139": "EVGO",

            "Q5176149": "CHARGEPOINT",
            "Q59773555": "ELECTRIFY_AMERICA",
            "Q61803820": "EVGO",
            "Q62065645": "BLINK",
            "Q64971203": "FLO",
            "Q105883058": "SHELL_RECHARGE",
            "Q109307156": "SHELL_RECHARGE", # Volta
        }

        OSM_BRAND_NAME_NETWORK_MAP = {
            "ABB": None, # Non-networked
            "ChargePoint": "CHARGEPOINT",
            "Enel": "ENEL_X",
            "Tesla, Inc.": None, # Ambiguous
            "Tesla Supercharger": "TESLA_SUPERCHARGER",
            "Volta": "SHELL_RECHARGE",
            "WattZilla": None, # Non-networked
        }

        OSM_BRAND_WIKIDATA_NETWORK_MAP = {
            # ABB Group
            "Q52825": None,
            # Tesla, Inc., currently ambiguous
            "Q478214": None,
            # AeroVironment
            "Q919300": None,

            "Q5176149": "CHARGEPOINT",
            "Q17089620": "TESLA_SUPERCHARGER",
            "Q61803820": "EVGO",
            "Q105883058": "SHELL_RECHARGE",
        }

        if "no:network" in tags:
            return "NON_NETWORKED"

        if "network:wikidata" in tags:
            if network := OSM_NETWORK_WIKIDATA_MAP[tags["network:wikidata"]]:
                return network

        if "network" in tags:
            if network := OSM_NETWORK_NAME_MAP[tags["network"]]:
                return network

        if "operator:wikidata" in tags:
            if network := OSM_OPERATOR_WIKIDATA_NETWORK_MAP[tags["operator:wikidata"]]:
                return network

        if "operator" in tags:
            if network := OSM_OPERATOR_NAME_MAP[tags["operator"]]:
                return network

        if "brand:wikidata" in tags:
            if network := OSM_BRAND_WIKIDATA_NETWORK_MAP[tags["brand:wikidata"]]:
                return network

        if "brand" in tags:
            if network := OSM_BRAND_NAME_NETWORK_MAP[tags["brand"]]:
                return network

        if "name" in tags:
            station_name = tags["name"].lower()

            if "supercharger" in station_name or "super charger" in station_name:
                return "TESLA_SUPERCHARGER"

            if "tesla" in station_name and "destination" in station_name:
                return "TESLA_DESTINATION"

        return None


    def parse_charging_station(self, element) -> StationFeature:
        station = StationFeature(
            address=AddressFeature(),
            charging_points=[],
            source=SourceFeature(
                quality="CURATED",
                system="OPEN_STREET_MAP",
            ),
            references=[],
        )
        station["references"].append(
            ReferenceFeature(
                identifier=f"{element["type"]}:{element["id"]}",
                system="OPEN_STREET_MAP",
            )
        )

        if element["type"] == "node":
            station["location"] = LocationFeature(
                latitude=element["lat"],
                longitude=element["lon"],
            )

        if element["type"] in ["way", "relation"]:
            station["location"] = LocationFeature(
                latitude=(element["bounds"]["minlat"] + element["bounds"]["maxlat"]) / 2,
                longitude=(element["bounds"]["minlon"] + element["bounds"]["maxlon"]) / 2,
            )

        tags = element["tags"]

        if "name" in tags:
            station_name = tags["name"]

            if station_name.lower() not in self.EXCLUDED_NAMES:
                station["name"] = station_name

        if "addr:housenumber" in tags and "addr:street" in tags:
            station["address"]["street_address"] = f'{tags["addr:housenumber"]} {tags["addr:street"]}'

        if "addr:city" in tags:
            station["address"]["city"] = tags["addr:city"]

        if "addr:state" in tags:
            station["address"]["state"] = tags["addr:state"]

        if "addr:postcode" in tags:
            station["address"]["zip_code"] = tags["addr:postcode"]

        if "ref:ocm" in tags:
            for ocm_id in tags["ref:ocm"].split(";"):
                station["references"].append(
                    ReferenceFeature(
                        identifier=ocm_id,
                        system="OPEN_CHARGE_MAP",
                    )
                )

        if "ref:afdc" in tags:
            for nrel_id in tags["ref:afdc"].split(";"):
                station["references"].append(
                    ReferenceFeature(
                        identifier=nrel_id,
                        system="ALTERNATIVE_FUEL_DATA_CENTER",
                    )
                )

        station["network"] = self.network_from_osm_tags(tags)

        if "ref:ocpi" in tags:
            for network_id in tags["ref:ocpi"].split(";"):
                station["references"].append(
                    ReferenceFeature(
                        identifier=self.normalize_ocpi_id(network_id, "L", "US", station["network"]),
                        system="OCPI",
                    )
                )

                station["network_id"] = self.normalize_ocpi_id(network_id, "L", "US", station["network"])

        return station

    def parse_charge_point(self, element) -> ChargingPointFeature:
        tags = element["tags"]

        charging_point = ChargingPointFeature(
            location=LocationFeature(
                latitude=element["lat"],
                longitude=element["lon"],
            ),
            references=[],
        )

        charging_point["references"].append(
            ReferenceFeature(
                identifier=f"{element["type"]}:{element["id"]}",
                system="OPEN_STREET_MAP",
            )
        )

        if "name" in tags and tags["name"].lower() not in self.EXCLUDED_NAMES:
            charging_point["name"] = tags["name"]
        elif "ref" in tags:
            charging_point["name"] = tags["ref"]

        charging_point._osm_network = self.network_from_osm_tags(tags)

        if "ref:ocpi" in tags:
            for network_id in tags["ref:ocpi"].split(";"):
                charging_point["references"].append(
                    ReferenceFeature(
                        identifier=self.normalize_ocpi_id(network_id, "E", "US", charging_point._osm_network),
                        system="OCPI",
                    )
                )

                charging_point["network_id"] = self.normalize_ocpi_id(network_id, "E", "US", charging_point._osm_network)

        return charging_point

    def format_ocpi_id(self, original_id, ocpi_type, country_code, network):
        NETWORK_TO_CPO = {
            "BLINK": "BLK",
            "CHARGEPOINT": "CPI",
            "EV_CONNECT": "EVC",
            "EVGO": "EVG",
            "FLO": "FLO",
        }

        if network not in NETWORK_TO_CPO:
            return original_id

        cpo_id = NETWORK_TO_CPO[network]

        if cpo_id == "FLO" and country_code == "US":
            cpo_id = "FL2"

        return f"{country_code}*{cpo_id}*{ocpi_type}{original_id}"

    def normalize_ocpi_id(self, ocpi_id, ocpi_type, country_code, network):
        if len(ocpi_id) < 7:
            return self.format_ocpi_id(ocpi_id, ocpi_type, country_code, network)

        if ocpi_id[2] == "*":
            return self.format_ocpi_id(ocpi_id, ocpi_type, country_code, network)

        ocpi_cc = ocpi_id[0:2]

        if ocpi_cc not in ["US", "CA"]:
            return self.format_ocpi_id(ocpi_id, ocpi_type, country_code, network)

        cpo_id = ocpi_id[2:5]

        id_type = ocpi_id[5]

        if id_type not in ["L", "E", "P"]:
            return self.format_ocpi_id(ocpi_id, ocpi_type, country_code, network)

        internal_id = ocpi_id[6:]

        return f"{ocpi_cc}*{cpo_id}*{ocpi_type}{internal_id}"

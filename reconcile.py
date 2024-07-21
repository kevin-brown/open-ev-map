from collections import defaultdict
from dataclasses import dataclass
from geopy import distance
import dataclasses
import enum
import geojson
import json


class PlugType(enum.Enum):
    J1772 = enum.auto()
    J1772_SOCKET = enum.auto()
    J1772_COMBO = enum.auto()
    CHADEMO = enum.auto()
    NACS = enum.auto()


class ChargingNetwork(enum.Enum):
    ABM = enum.auto()
    AMPED_UP = enum.auto()
    AMPUP = enum.auto()
    BLINK = enum.auto()
    CHARGEPOINT = enum.auto()
    ELECTRIC_ERA = enum.auto()
    ELECTRIFY_AMERICA = enum.auto()
    EV_CONNECT = enum.auto()
    EV_GATEWAY = enum.auto()
    EVGO = enum.auto()
    EVPASSPORT = enum.auto()
    FLO = enum.auto()
    NOODOE = enum.auto()
    RED_E = enum.auto()
    RIVIAN_ADVENTURE = enum.auto()
    SEVEN_CHARGE = enum.auto()
    SHELL_RECHARGE = enum.auto()
    TESLA_DESTINATION = enum.auto()
    TESLA_SUPERCHARGER = enum.auto()
    TURN_ON_GREEN = enum.auto()
    VOLTA = enum.auto()


@dataclass
class ChargingPort:
    plug: PlugType


@dataclass
class ChargingPortGroup:
    charging_ports: list[ChargingPort] = dataclasses.field(default_factory=list)

    network_id: str = ""


@dataclass
class ChargingPoint:
    charging_port_groups: list[ChargingPortGroup] = dataclasses.field(default_factory=list)

    name: str = ""
    latitude: int = None
    longitude: int = None

    osm_id: int = None
    nrel_id: int = None
    network_id: str = ""


@dataclass
class Station:
    charging_points: list[ChargingPoint] = dataclasses.field(default_factory=list)

    name: str = ""
    network: ChargingNetwork = None

    latitude: int = None
    longitude: int = None
    street_address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""

    osm_id: int = None
    nrel_id: int = None
    network_id: str = ""


def nrel_group_chargepoint(nrel_stations: list[Station]) -> list[Station]:
    cleaned_stations = []

    deduplicated_stations = defaultdict(list)

    for station in nrel_stations:
        if station.network != ChargingNetwork.CHARGEPOINT:
            cleaned_stations.append(station)
            continue

        station_location = (station.latitude, station.longitude)

        duplicate = False

        for other_station in nrel_stations:        
            if other_station.network != ChargingNetwork.CHARGEPOINT:
                continue

            if station.nrel_id == other_station.nrel_id:
                continue

            if station.nrel_id in deduplicated_stations[other_station.nrel_id]:
                duplicate = True
                break

            if station.street_address != other_station.street_address:
                continue

            other_location = (other_station.latitude, other_station.longitude)

            station_distance = distance.great_circle(station_location, other_location)

            if station_distance.miles > 0.05:
                continue

            combined_charging_points = [*station.charging_points, *other_station.charging_points]

            combined_station = dataclasses.replace(station, charging_points=combined_charging_points, name=f"{station.name};{other_station.name}", network_id=f"{station.network_id};{other_station.network_id}")

            station = combined_station

            deduplicated_stations[station.nrel_id].append(other_station.nrel_id)

        if not duplicate:
            cleaned_stations.append(station)

    return cleaned_stations


def normalize_nrel_data(nrel_raw_data) -> list[Station]:
    NREL_PLUG_MAP = {
        "CHADEMO": PlugType.CHADEMO,
        "TESLA": PlugType.NACS,

        "J1772": PlugType.J1772,
        "J1772COMBO": PlugType.J1772_COMBO,
    }

    NREL_NETWORK_MAP = {
        "7CHARGE": ChargingNetwork.SEVEN_CHARGE,
        "ABM": ChargingNetwork.ABM,
        "AMPED_UP": ChargingNetwork.AMPED_UP,
        "AMPUP": ChargingNetwork.AMPUP,
        "Blink Network": ChargingNetwork.BLINK,
        "ChargePoint Network": ChargingNetwork.CHARGEPOINT,
        "CHARGESMART_EV": None,
        "Electrify America": ChargingNetwork.ELECTRIFY_AMERICA,
        "EV Connect": ChargingNetwork.EV_CONNECT,
        "EVGATEWAY": ChargingNetwork.EV_GATEWAY,
        "eVgo Network": ChargingNetwork.EVGO,
        "FLO": ChargingNetwork.FLO,
        "LIVINGSTON": None,
        "LOOP": None,
        "NOODOE": ChargingNetwork.NOODOE,
        "Non-Networked": None,
        "POWER_NODE": ChargingNetwork.ELECTRIC_ERA,
        "RED_E": ChargingNetwork.RED_E,
        "RIVIAN_ADVENTURE": ChargingNetwork.RIVIAN_ADVENTURE,
        "SHELL_RECHARGE": ChargingNetwork.SHELL_RECHARGE,
        "SWTCH": None,
        "Tesla": ChargingNetwork.TESLA_SUPERCHARGER,
        "Tesla Destination": ChargingNetwork.TESLA_DESTINATION,
        "TURNONGREEN": ChargingNetwork.TURN_ON_GREEN,
        "Volta": ChargingNetwork.VOLTA,
    }

    stations = []

    for nrel_station in nrel_raw_data["fuel_stations"]:
        station = Station(
            name=nrel_station["station_name"],
            network=NREL_NETWORK_MAP[nrel_station["ev_network"]],
            nrel_id=nrel_station["id"],

            latitude=nrel_station["latitude"],
            longitude=nrel_station["longitude"],

            street_address=nrel_station["street_address"],
            city=nrel_station["city"],
            state=nrel_station["state"],
            zip_code=nrel_station["zip"],
        )

        charging_points = []

        if "ev_network_ids" in nrel_station:
            station.network_id = nrel_station["ev_network_ids"].get("station", [None])[0]

            charging_port_groups = []

            for nrel_post_id in nrel_station["ev_network_ids"].get("posts", []):
                charging_ports = []

                for nrel_plug_type in nrel_station["ev_connector_types"]:
                    if nrel_plug_type not in NREL_PLUG_MAP:
                        continue

                    charging_port = ChargingPort(
                        plug=NREL_PLUG_MAP[nrel_plug_type],
                    )

                    charging_ports.append(charging_port)

                charging_port_group = ChargingPortGroup(
                    network_id=nrel_post_id,
                    charging_ports=charging_ports
                )

                charging_port_groups.append(charging_port_group)

            charging_point = ChargingPoint(
                network_id=station.network_id,
                nrel_id=station.nrel_id,
                name=station.name,
                charging_port_groups=charging_port_groups,
                latitude=nrel_station["latitude"],
                longitude=nrel_station["longitude"],
            )

            charging_points.append(charging_point)

        station.charging_points = charging_points

        stations.append(station)

    stations = nrel_group_chargepoint(stations)

    return stations


def osm_parse_charging_station(osm_element) -> Station:
    OSM_NETWORK_NAME_MAP = {
        "AmpUp": ChargingNetwork.AMPUP,
        "ChargePoint": ChargingNetwork.CHARGEPOINT,
        "EV Connect": ChargingNetwork.EV_CONNECT,
        "EVPassport": ChargingNetwork.EVPASSPORT,
        "Tesla, Inc.": ChargingNetwork.TESLA_SUPERCHARGER,
        "Tesla Supercharger": ChargingNetwork.TESLA_SUPERCHARGER,
        "Volta": ChargingNetwork.VOLTA,
    }

    OSM_NETWORK_WIKIDATA_MAP = {
        "Q478214": ChargingNetwork.TESLA_SUPERCHARGER,
        "Q5176149": ChargingNetwork.CHARGEPOINT,
        "Q59773555": ChargingNetwork.ELECTRIFY_AMERICA,
        "Q61803820": ChargingNetwork.EVGO,
        "Q62065645": ChargingNetwork.BLINK,
        "Q109307156": ChargingNetwork.VOLTA,
    }

    station = Station(
        osm_id=osm_element["id"],
    )

    if osm_element["type"] == "node":
        station.latitude = osm_element["lat"]
        station.longitude = osm_element["lon"]

    if osm_element["type"] in ["way", "relation"]:
        station.latitude = (osm_element["bounds"]["minlat"] + osm_element["bounds"]["maxlat"]) / 2
        station.longitude = (osm_element["bounds"]["minlon"] + osm_element["bounds"]["maxlon"]) / 2

    tags = osm_element["tags"]

    if "name" in tags:
        station.name = tags["name"]

    if station.network is None and "network:wikidata" in tags:
        station.network = OSM_NETWORK_WIKIDATA_MAP.get(tags["network:wikidata"])

    if station.network is None and "network" in tags:
        station.network = OSM_NETWORK_NAME_MAP.get(tags["network"])

    if station.network is None and "operator:wikidata" in tags:
        station.network = OSM_NETWORK_WIKIDATA_MAP.get(tags["operator:wikidata"])

    if station.network is None and "operator" in tags:
        station.network = OSM_NETWORK_NAME_MAP.get(tags["operator"])

    if station.network is None and "brand:wikidata" in tags:
        station.network = OSM_NETWORK_WIKIDATA_MAP.get(tags["brand:wikidata"])

    if station.network is None and "brand" in tags:
        station.network = OSM_NETWORK_NAME_MAP.get(tags["brand"])

    return station


def normalize_osm_data(osm_raw_data) -> list[Station]:
    stations = []

    for osm_element in osm_raw_data["elements"]:
        if osm_element["tags"].get("amenity") == "charging_station":
            stations.append(osm_parse_charging_station(osm_element))

    return stations


def combine_tesla_superchargers(all_stations: list[Station]) -> list[Station]:
    combined_stations = []
    tesla_stations = []

    for station in all_stations:
        if station.network != ChargingNetwork.TESLA_SUPERCHARGER:
            combined_stations.append(station)
        else:
            tesla_stations.append(station)

    for first_station in tesla_stations:
        if getattr(first_station, "duplicated", False):
            continue

        first_location = (first_station.latitude, first_station.longitude)

        combined = False

        for second_station in tesla_stations:
            if first_station == second_station:
                continue

            if getattr(second_station, "duplicated", False):
                continue

            second_location = (second_station.latitude, second_station.longitude)

            station_distance = distance.great_circle(first_location, second_location)

            if station_distance.miles > 0.1:
                continue

            combined_station = dataclasses.replace(first_station)

            CLONED_ATTRS = ['name', 'osm_id', 'nrel_id', 'network_id', 'street_address', 'city', 'state', 'zip_code']

            for attr in CLONED_ATTRS:
                second_value = getattr(second_station, attr)
                if second_value:
                    setattr(combined_station, attr, second_value)

            combined_stations.append(combined_station)
        
            first_station.duplicated = True
            second_station.duplicated = True

            combined = True

            break

        if not combined:
            combined_stations.append(first_station)

    return combined_stations


def combine_stations(all_stations: list[Station]) -> list[Station]:
    all_stations = combine_tesla_superchargers(all_stations)
    combined_stations = []

    for first_station in all_stations:
        if getattr(first_station, "duplicated", False):
            continue

        first_location = (first_station.latitude, first_station.longitude)

        combined = False

        for second_station in all_stations:
            if getattr(second_station, "duplicated", False):
                continue

            if first_station.nrel_id == second_station.nrel_id:
                continue

            if first_station.osm_id == second_station.osm_id:
                continue

            if first_station.network is None:
                continue

            if second_station.network is None:
                continue

            if first_station.network != second_station.network:
                continue

            second_location = (second_station.latitude, second_station.longitude)

            station_distance = distance.great_circle(first_location, second_location)

            if station_distance.miles > 0.05:
                continue

            if first_station.osm_id is not None and second_station.osm_id is not None:
                continue

            combined_station = dataclasses.replace(first_station)

            CLONED_ATTRS = ['name', 'osm_id', 'nrel_id', 'network_id', 'street_address', 'city', 'state', 'zip_code']

            for attr in CLONED_ATTRS:
                second_value = getattr(second_station, attr)
                if second_value:
                    setattr(combined_station, attr, second_value)

            first_station.duplicated = True
            second_station.duplicated = True

            combined = True
            combined_stations.append(combined_station)

            break

        if not combined:
            combined_stations.append(first_station)

    return combined_stations


with open("nrel.json", "r") as nrel_fh:
    nrel_raw_data = json.load(nrel_fh)

with open("osm.json", "r") as osm_fh:
    osm_raw_data = json.load(osm_fh)

nrel_data = normalize_nrel_data(nrel_raw_data)
osm_data = normalize_osm_data(osm_raw_data)

combined_data = combine_stations([*nrel_data, *osm_data])

station_features = geojson.FeatureCollection([])
for station in combined_data:
    station_point = geojson.Point(
        coordinates=(station.longitude, station.latitude)
    )

    station_properties = {
        "name": station.name,
    }
    if station.network:
        station_properties["network"] = station.network.name
    if station.osm_id:
        station_properties["osm_id"] = station.osm_id
    if station.nrel_id:
        station_properties["nrel_id"] = station.nrel_id
    if station.network_id:
        station_properties["network_id"] = station.network_id

    if station.street_address:
        station_properties["street_address"] = station.street_address
    if station.city:
        station_properties["city"] = station.city
    if station.state:
        station_properties["state"] = station.state
    if station.zip_code:
        station_properties["zip_code"] = station.zip_code

    station_feature = geojson.Feature(
        geometry=station_point,
        properties=station_properties,
    )
    station_features["features"].append(station_feature)

with open("stations.geojson", "w") as stations_fh:
    geojson.dump(station_features, stations_fh)
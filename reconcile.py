from collections import defaultdict
from dataclasses import dataclass
from geopy import distance
import dataclasses
import enum
import json


class PlugType(enum.Enum):
    J1772 = enum.auto()
    J1772_SOCKET = enum.auto()
    J1772_COMBO = enum.auto()
    CHADEMO = enum.auto()
    NACS = enum.auto()


class ChargingNetwork(enum.Enum):
    AMPUP = enum.auto()
    BLINK = enum.auto()
    CHARGEPOINT = enum.auto()
    ELECTRIFY_AMERICA = enum.auto()
    EV_CONNECT = enum.auto()
    EVGO = enum.auto()
    EVPASSPORT = enum.auto()
    TESLA = enum.auto()
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

            other_location = (station.latitude, station.longitude)

            station_distance = distance.great_circle(station_location, other_location)

            if station_distance.miles > 0.05:
                continue

            combined_charging_points = [*station.charging_points, *other_station.charging_points]

            combined_station = dataclasses.replace(station, charging_points=combined_charging_points, name="", network_id="")

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
        "ChargePoint Network": ChargingNetwork.CHARGEPOINT,
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

        if "ev_network_ids" in nrel_station:
            station.network_id = nrel_station["ev_network_ids"]["station"][0]

            charging_points = []
            charging_port_groups = []

            for nrel_post_id in nrel_station["ev_network_ids"]["posts"]:
                charging_ports = []

                for nrel_plug_type in nrel_station["ev_connector_types"]:
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
        "Tesla, Inc.": ChargingNetwork.TESLA,
        "Tesla Supercharger": ChargingNetwork.TESLA,
        "Volta": ChargingNetwork.VOLTA,
    }

    OSM_NETWORK_WIKIDATA_MAP = {
        "Q478214": ChargingNetwork.TESLA,
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


with open("nrel.json", "r") as nrel_fh:
    nrel_raw_data = json.load(nrel_fh)

with open("osm.json", "r") as osm_fh:
    osm_raw_data = json.load(osm_fh)

nrel_data = normalize_nrel_data(nrel_raw_data)
osm_data = normalize_osm_data(osm_raw_data)

for osm_site in osm_data:
    print(osm_site)

from collections import defaultdict
from dataclasses import dataclass, field
from geopy import distance
import enum
import json


class PlugType(enum.Enum):
    J1772 = enum.auto()
    J1772_SOCKET = enum.auto()
    J1772_COMBO = enum.auto()
    CHADEMO = enum.auto()
    NACS = enum.auto()


class ChargingNetwork(enum.Enum):
    CHARGEPOINT = enum.auto()


@dataclass
class ChargingPort:
    plug: PlugType


@dataclass
class ChargingPortGroup:
    charging_ports: list[ChargingPort] = field(default_factory=list)

    network_id: str = ""


@dataclass
class ChargingPoint:
    charging_port_groups: list[ChargingPortGroup] = field(default_factory=list)

    name: str = ""
    latitude: int = None
    longitude: int = None

    osm_id: int = None
    network_id: str = ""


@dataclass
class Station:
    charging_points: list[ChargingPoint] = field(default_factory=list)

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

            combined_station = Station(
                name="",
                network=ChargingNetwork.CHARGEPOINT,
                charging_points=combined_charging_points,
                nrel_id=station.nrel_id,
                street_address=station.street_address,
                latitude=station.latitude,
                longitude=station.longitude,
            )

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


def normalize_osm_data(osm_raw_data) -> list[Station]:
    pass


with open("nrel.json", "r") as nrel_fh:
    nrel_raw_data = json.load(nrel_fh)

with open("osm.json", "r") as osm_fh:
    osm_raw_data = json.load(osm_fh)

nrel_data = normalize_nrel_data(nrel_raw_data)
osm_data = normalize_osm_data(osm_raw_data)

for nrel_site in nrel_data:
    if len(nrel_site.charging_points) > 1:
        print(nrel_site)
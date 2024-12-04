from collections import defaultdict
from dataclasses import dataclass
from geopy import distance
from typing import NamedTuple, Optional, Self
import dataclasses
import enum
import geojson
import json
import pathlib
import queue
import shapely


@dataclass(frozen=True)
class Location:
    latitude: int
    longitude: int

    @property
    def coordinates(self):
        return (self.latitude, self.longitude)

    @property
    def point(self) -> shapely.Point:
        return shapely.Point(self.latitude, self.longitude)

    def __lt__(self, other) -> bool:
        return self.coordinates < other.coordinates


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
    AUTEL = enum.auto()
    BLINK = enum.auto()
    CHARGEPOINT = enum.auto()
    ELECTRIC_ERA = enum.auto()
    ELECTRIFY_AMERICA = enum.auto()
    ENEL_X = enum.auto()
    EV_CONNECT = enum.auto()
    EV_GATEWAY = enum.auto()
    EVGO = enum.auto()
    EVPASSPORT = enum.auto()
    FLO = enum.auto()
    GREENSPOT = enum.auto()
    LOOP = enum.auto()
    NOODOE = enum.auto()
    RED_E = enum.auto()
    RIVIAN_ADVENTURE = enum.auto()
    SEVEN_CHARGE = enum.auto()
    SHELL_RECHARGE = enum.auto()
    TESLA_DESTINATION = enum.auto()
    TESLA_SUPERCHARGER = enum.auto()
    TURN_ON_GREEN = enum.auto()
    VOLTA = enum.auto()

    NON_NETWORKED = enum.auto()


class SourceLocationQualityScore(enum.Enum):
    CURATED = 40
    ORIGINAL = 30
    PARTNER = 20
    AGGREGATED = 10


class SourceLocation(NamedTuple):
    system: str
    quality: SourceLocationQualityScore


class SourcedValue[T](NamedTuple):
    source: SourceLocation
    value: T

    def __repr__(self):
        return f"<SourcedValue({self.source.system!r}, {self.value!r})>"


class SourcedAttribute[T]:
    values: set[SourcedValue[T]]
    multiple: bool

    def __init__(self, multiple=False):
        self.values = set()
        self.multiple = multiple

    def __repr__(self):
        return f"<SourcedAttribute({self.values!r})>"

    def set(self, value: SourcedValue[T]):
        if not value.value:
            return

        self.values.add(value)

    def get(self) -> T:
        if self.multiple:
            return sorted(set(self.all()))

        if not self.values:
            return ""

        raw_values = list(sorted(set(self.all())))

        if not isinstance(raw_values[0], str):
            return raw_values[0]

        return ";".join(raw_values)

    def all(self) -> list[T]:
        if not self.values:
            return []

        return [val.value for val in self.values]

    def extend(self, other: Self):
        self.values.update(other.values)


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
    location: SourcedAttribute[Location] = dataclasses.field(default_factory=SourcedAttribute)

    ocm_id: SourcedAttribute[int] = dataclasses.field(default_factory=SourcedAttribute)
    osm_id: SourcedAttribute[int] = dataclasses.field(default_factory=SourcedAttribute)
    nrel_id: SourcedAttribute[int] = dataclasses.field(default_factory=SourcedAttribute)

    network_id: SourcedAttribute[str] = dataclasses.field(default_factory=SourcedAttribute)


@dataclass
class Station:
    charging_points: list[ChargingPoint] = dataclasses.field(default_factory=list)

    name: SourcedAttribute[str] = dataclasses.field(default_factory=SourcedAttribute)
    network: Optional[ChargingNetwork] = None

    location: SourcedAttribute[Location] = dataclasses.field(default_factory=SourcedAttribute)
    street_address: SourcedAttribute[str] = dataclasses.field(default_factory=SourcedAttribute)
    city: SourcedAttribute[str] = dataclasses.field(default_factory=SourcedAttribute)
    state: SourcedAttribute[str] = dataclasses.field(default_factory=SourcedAttribute)
    zip_code: SourcedAttribute[str] = dataclasses.field(default_factory=SourcedAttribute)

    osm_id: SourcedAttribute[list[int]] = dataclasses.field(default_factory=lambda: SourcedAttribute(multiple=True))
    nrel_id: SourcedAttribute[list[int]] = dataclasses.field(default_factory=lambda: SourcedAttribute(multiple=True))
    ocm_id: SourcedAttribute[list[int]] = dataclasses.field(default_factory=lambda: SourcedAttribute(multiple=True))

    network_id: SourcedAttribute[str] = dataclasses.field(default_factory=SourcedAttribute)


def get_station_distance(first_station: Station, second_station: Station) -> distance.Distance:
    first_locations = first_station.location.all()
    second_locations = second_station.location.all()

    lowest_station_distance = distance.Distance(miles=2**8)

    for first_location in first_locations:
        for second_location in second_locations:
            first_coordinates = first_location.coordinates
            second_coordinates = second_location.coordinates

            station_distance = distance.great_circle(first_coordinates, second_coordinates)

            if station_distance.miles < lowest_station_distance.miles:
                lowest_station_distance = station_distance

    return lowest_station_distance


def merge_stations(first_station: Station, second_station: Station) -> Station:
    combined_station = Station()

    combined_station.name.extend(first_station.name)
    combined_station.name.extend(second_station.name)

    combined_station.nrel_id.extend(first_station.nrel_id)
    combined_station.nrel_id.extend(second_station.nrel_id)

    combined_station.osm_id.extend(first_station.osm_id)
    combined_station.osm_id.extend(second_station.osm_id)

    combined_station.ocm_id.extend(first_station.ocm_id)
    combined_station.ocm_id.extend(second_station.ocm_id)

    combined_station.location.extend(first_station.location)
    combined_station.location.extend(second_station.location)

    combined_station.street_address.extend(first_station.street_address)
    combined_station.street_address.extend(second_station.street_address)

    combined_station.city.extend(first_station.city)
    combined_station.city.extend(second_station.city)

    combined_station.state.extend(first_station.state)
    combined_station.state.extend(second_station.state)

    combined_station.zip_code.extend(first_station.zip_code)
    combined_station.zip_code.extend(second_station.zip_code)

    combined_station.network_id.extend(first_station.network_id)
    combined_station.network_id.extend(second_station.network_id)

    if first_station.network is not None:
        combined_station.network = first_station.network

    if second_station.network is not None:
        if second_station.network != combined_station.network:
            print("Conflicting networks when merging stations:", first_station.network, second_station.network, combined_station)

        combined_station.network = second_station.network

    first_charging_points = first_station.charging_points
    second_charging_points = second_station.charging_points

    combined_station.charging_points = combine_charging_points(first_charging_points, second_charging_points)

    return combined_station


def combine_charging_points(first_points: list[ChargingPoint], second_points: list[ChargingPoint]) -> list[ChargingPoint]:
    if first_points and not second_points:
        return first_points

    if second_points and not first_points:
        return second_points

    if not first_points and not second_points:
        return []

    first_network_ids = set(point.network_id.get() for point in first_points if point.network_id.get())
    second_network_ids = set(point.network_id.get() for point in second_points if point.network_id.get())

    if first_network_ids or second_network_ids:
        return combine_charging_points_by_id(first_points, second_points)

    first_names = set(point.name for point in first_points if point.name)
    second_names = set(point.name for point in second_points if point.name)

    if first_names or second_names:
        return combine_charging_points_by_name(first_points, second_points)

    if len(first_points) != len(second_points):
        return [*first_points, *second_points]

    return first_points


def combine_charging_points_by_id(first_points: list[ChargingPoint], second_points: list[ChargingPoint]) -> list[ChargingPoint]:
    network_ids_to_charging_points = defaultdict(list)

    for charging_point in [*first_points, *second_points]:
        network_ids_to_charging_points[charging_point.network_id.get()].append(charging_point)

    combined_points = []

    for network_id, charging_points in network_ids_to_charging_points.items():
        if not network_id:
            # combined_points.extend(charging_points)

            continue

        combined_point = charging_points[0]

        if len(charging_points) > 1:
            for charging_point in charging_points:
                combined_point = merge_charging_points(combined_point, charging_point)

        combined_points.append(combined_point)

    return combined_points


def combine_charging_points_by_name(first_points: list[ChargingPoint], second_points: list[ChargingPoint]) -> list[ChargingPoint]:
    names_to_charging_points = defaultdict(list)

    for charging_point in [*first_points, *second_points]:
        names_to_charging_points[charging_point.name].append(charging_point)

    combined_points = []

    for name, charging_points in names_to_charging_points.items():
        if not name:
            # combined_points.extend(charging_points)

            continue

        combined_point = charging_points[0]

        if len(charging_points) > 1:
            for charging_point in charging_points:
                combined_point = merge_charging_points(combined_point, charging_point)

        combined_points.append(combined_point)

    return combined_points


def merge_charging_points(first_point: ChargingPoint, second_point: ChargingPoint) -> ChargingPoint:
    combined_charging_point = ChargingPoint(
        name="",
    )

    if first_point.name:
        combined_charging_point.name = first_point.name

    if second_point.name:
        combined_charging_point.name = second_point.name

    combined_charging_point.location.extend(first_point.location)
    combined_charging_point.location.extend(second_point.location)

    combined_charging_point.nrel_id.extend(first_point.nrel_id)
    combined_charging_point.nrel_id.extend(second_point.nrel_id)

    combined_charging_point.ocm_id.extend(first_point.ocm_id)
    combined_charging_point.ocm_id.extend(second_point.ocm_id)

    combined_charging_point.osm_id.extend(first_point.osm_id)
    combined_charging_point.osm_id.extend(second_point.osm_id)

    combined_charging_point.network_id.extend(first_point.network_id)
    combined_charging_point.network_id.extend(second_point.network_id)

    combined_charging_point.charging_port_groups = combine_charging_port_groups(first_point.charging_port_groups, second_point.charging_port_groups)

    return combined_charging_point


def combine_charging_port_groups(first_groups: list[ChargingPortGroup], second_groups: list[ChargingPortGroup]) -> list[ChargingPortGroup]:
    if not first_groups:
        return second_groups

    if not second_groups:
        return first_groups

    network_ids_to_charging_ports = defaultdict(list)

    for charging_port_group in [*first_groups, *second_groups]:
        network_ids_to_charging_ports[charging_port_group.network_id].append(charging_port_group)

    if len(network_ids_to_charging_ports) == 1:
        network_id = list(network_ids_to_charging_ports.keys())[0]

        if not network_id:
            return first_groups

    combined_groups = []

    for network_id, charging_ports in network_ids_to_charging_ports.items():
        if not network_id:
            continue

        combined_group = charging_ports[0]

        if len(charging_ports) > 1:
            for charging_port_group in charging_ports:
                combined_group = merge_charging_port_groups(combined_group, charging_port_group)

        combined_groups.append(combined_group)

    return combined_groups


def merge_charging_port_groups(first_group: ChargingPortGroup, second_group: ChargingPortGroup):
    combined_group = ChargingPortGroup(
        charging_ports=[],
    )

    if first_group.network_id:
        combined_group.network_id = first_group.network_id
    elif second_group.network_id:
        combined_group.network_id = second_group.network_id

    for charging_port in [*first_group.charging_ports, *second_group.charging_ports]:
        if charging_port in combined_group.charging_ports:
            continue

        combined_group.charging_ports.append(charging_port)

    return combined_group


def normalize_address_street_address(street_address: str) -> str:
    STREET_TYPE_MAP = {
        "ave": "Avenue",
        "blvd": "Boulevard",
        "cir": "Circle",
        "ct": "Court",
        "dr": "Drive",
        "expy": "Expressway",
        "hwy": "Highway",
        "ln": "Lane",
        "pl": "Place",
        "pkwy": "Parkway",
        "rd": "Road",
        "st": "Street",
        "sq": "Square",
        "tpke": "Turnpike",
    }

    PREFIX_NUMBER_MAP = {
        "One": "1",
    }

    abbreviated_street_names = {
        "N": "North",
        "E": "East",
        "S": "South",
        "W": "West",
    }

    if " " in street_address:
        address_parts = list(filter(None, street_address.split(" ")))
        street_type = address_parts[-1]
        is_extension = False

        if street_type.lower().startswith("ext"):
            street_type = address_parts[-2]
            del address_parts[-1]
            is_extension = True

        if street_type.endswith(".") or street_type.endswith(","):
            street_type = street_type[:-1]

        street_type = street_type.lower()

        if street_type in STREET_TYPE_MAP:
            address_parts[-1] = STREET_TYPE_MAP[street_type]

        if address_parts[0] in PREFIX_NUMBER_MAP:
            address_parts[0] = PREFIX_NUMBER_MAP[address_parts[0]]

        if len(address_parts) > 3 and address_parts[1] in list(abbreviated_street_names.keys()):
            address_parts[1] = abbreviated_street_names[address_parts[1]]

        if is_extension:
            address_parts.append("Extension")

        street_address = " ".join(address_parts)

    if street_address.endswith(".") or street_address.endswith(","):
        street_address = street_address[:-1]

    return street_address


def guess_charging_point_groups(capacity: int, plug_counts: dict[PlugType, int]) -> list[ChargingPoint]:
    charging_points = []

    if sum(plug_counts.values()) == capacity:
        for socket_type, socket_count in plug_counts.items():
            for _ in range(socket_count):
                charging_port_group = ChargingPortGroup(
                    charging_ports=[ChargingPort(plug=socket_type)]
                )
                charging_point = ChargingPoint(charging_port_groups=[charging_port_group])
                charging_points.append(charging_point)
    elif capacity == 1 and plug_counts:
        charging_port_group = ChargingPortGroup()

        for socket_type in plug_counts.keys():
            charging_port = ChargingPort(plug=socket_type)
            charging_port_group.charging_ports.append(charging_port)

        charging_point = ChargingPoint(charging_port_groups=[charging_port_group])

        charging_points.append(charging_point)
    elif all(plug_value == capacity for plug_value in plug_counts.values()):
        for _ in enumerate(range(capacity)):
            charging_port_group = ChargingPortGroup()

            for plug_type in plug_counts.keys():
                charging_port = ChargingPort(plug=plug_type)
                charging_port_group.charging_ports.append(charging_port)

            charging_point = ChargingPoint(charging_port_groups=[charging_port_group])
            charging_points.append(charging_point)
    elif all(plug_value % capacity == 0 for plug_value in plug_counts.values()):
        for _ in enumerate(range(capacity)):
            charging_port_groups = []

            for plug_type, plug_count in plug_counts.items():
                split_count = plug_count // capacity

                for _ in enumerate(range(split_count)):
                    charging_port = ChargingPort(plug=plug_type)
                    charging_port_group = ChargingPortGroup(charging_ports=[charging_port])
                    charging_port_groups.append(charging_port_group)

            charging_point = ChargingPoint(charging_port_groups=charging_port_groups)
            charging_points.append(charging_point)
    elif capacity and plug_counts:
        print("Uneven plugs to capacity detected:", capacity, plug_counts)

    return charging_points


def normalize_ocm_data(ocm_raw_data) -> list[Station]:
    stations = []

    OCM_OPERATOR_TO_NETWORK_MAP = {
        1: None,
        5: ChargingNetwork.CHARGEPOINT,
        9: ChargingNetwork.BLINK,
        15: ChargingNetwork.EVGO,
        23: ChargingNetwork.TESLA_SUPERCHARGER, # Tesla-only
        50: ChargingNetwork.VOLTA,
        59: ChargingNetwork.SHELL_RECHARGE,
        89: ChargingNetwork.FLO,
        1242: ChargingNetwork.CHARGEPOINT, # GE WattStation legacy
        3318: ChargingNetwork.ELECTRIFY_AMERICA,
        3372: ChargingNetwork.EV_CONNECT,
        3426: ChargingNetwork.BLINK,
        3534: ChargingNetwork.TESLA_SUPERCHARGER, # Any vehicles
        3619: ChargingNetwork.AMPUP,
        3789: ChargingNetwork.ELECTRIC_ERA,

        45: ChargingNetwork.NON_NETWORKED, # Private Owner

        6: None, # Nissan
        11: None, # AFDC Import
        26: None, # AeroVironment
        31: None, # Clipper Creek
        39: None, # SemaConnect
        42: None, # Eaton
        3293: None, # Revolta Egypt
        3460: None, # PEA Volta
        3493: None, # SWTCH
        3620: None, # Livingston Charge Port / solution.energy
    }

    OCM_CONNECTION_TYPE_TO_PLUG_MAP = {
        1: PlugType.J1772,
        2: PlugType.CHADEMO,
        27: PlugType.NACS,
        30: PlugType.NACS,
        32: PlugType.J1772_COMBO,

        0: None, # Unspecified
        9: None, # NEMA 5-20R
        22: None, # NEMA 5-15R
    }

    OCM_LONG_STATE_TO_SHORT_MAP = {
        "berkshire": None,
        "california": "CA",
        "connecticut": "CT",
        "mas": "MA",
        "massachusetts": "MA",
        "middlesex county": None,
        "new hampshire": "NH",
        "rhode island": "RI",
    }

    for ocm_station in ocm_raw_data:
        if ocm_station["DataProviderID"] in [15, ]:
            continue

        if ocm_station.get("StatusTypeID") in [100, ]:
            continue

        station = Station()
        station.ocm_id.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), ocm_station["ID"]))
        ocm_address = ocm_station["AddressInfo"]

        if "Title" in ocm_address:
            station_name = ocm_address["Title"]

            station.name.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), station_name))

        station_location = Location(latitude=ocm_address["Latitude"], longitude=ocm_address["Longitude"])
        station.location.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), station_location))

        if "OperatorID" in ocm_station:
            station.network = OCM_OPERATOR_TO_NETWORK_MAP[ocm_station["OperatorID"]]

        station_state = ocm_address.get("StateOrProvince")
        station_zip_code = ocm_address.get("Postcode")

        if station_state and len(station_state) > 2 and ocm_address["CountryID"] == 2:
            station_state = OCM_LONG_STATE_TO_SHORT_MAP[station_state.lower()]

        if station_zip_code and len(station_zip_code) < 5 and ocm_address["CountryID"] == 2:
            station_zip_code = station_zip_code.rjust(5, "0")

        station.street_address.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), normalize_address_street_address(ocm_address["AddressLine1"])))
        station.city.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), ocm_address["Town"]))
        station.state.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), station_state))
        station.zip_code.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), station_zip_code))

        if ocm_station["DataProviderID"] == 2:
            station.nrel_id.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), int(ocm_station["DataProvidersReference"])))

        if station.network == ChargingNetwork.TESLA_SUPERCHARGER:
            if ocm_station["Connections"][0]["CurrentTypeID"] in [10, 20]:
                station.network = ChargingNetwork.TESLA_DESTINATION

        plug_counts: dict[PlugType, int] = {}
        charge_point_count = ocm_station.get("NumberOfPoints")

        for ocm_connection in ocm_station["Connections"]:
            plug_type = OCM_CONNECTION_TYPE_TO_PLUG_MAP[ocm_connection["ConnectionTypeID"]]

            if not plug_type:
                continue

            plug_count = ocm_connection.get("Quantity", 1)

            if not plug_count:
                continue

            if plug_type not in plug_counts:
                plug_counts[plug_type] = 0

            plug_counts[plug_type] += plug_count

        if ocm_station["DataProviderID"] != 2 and station.network not in [ChargingNetwork.TESLA_SUPERCHARGER] and charge_point_count and plug_counts:
            station.charging_points = guess_charging_point_groups(charge_point_count, plug_counts)

        for charging_point in station.charging_points:
            charging_point.location.extend(station.location)

        stations.append(station)

    return stations


def filter_out_unknown_network(station: Station):
    return station.network is not None


def filter_out_networked(station: Station):
    return station.network == "NON_NETWORKED"


def filter_out_non_networked(station: Station):
    return station.network != "NON_NETWORKED"


def combine_tesla_superchargers(all_stations: list[Station]) -> list[Station]:
    def check_tesla_distance(first_station, second_station):
        station_distance = get_station_distance(first_station, second_station)

        return station_distance.miles < 0.1

    def filter_out_non_tesla_supercharger(station):
        return station.network == "TESLA_SUPERCHARGER"

    return combine_stations_with_check(all_stations, check_tesla_distance, [filter_out_non_tesla_supercharger])


def combine_networked_stations_at_same_address(all_stations: list[Station]) -> list[Station]:
    def check_same_address(first_station: Station, second_station: Station) -> bool:
        if not station_networks_match(first_station, second_station):
            return False

        first_addresses = set(map(str.lower, first_station.street_address.all()))
        second_addresses = set(map(str.lower, second_station.street_address.all()))

        if not (first_addresses & second_addresses):
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.5:
            return False

        return True

    def filter_missing_address(station):
        return station.street_address.all()

    return combine_stations_with_check(all_stations, check_same_address, [filter_out_non_networked, filter_out_unknown_network, filter_missing_address])

def combine_networked_stations_near_known_address(all_stations: list[Station]) -> list[Station]:
    def check_same_address(first_station: Station, second_station: Station) -> bool:
        if not station_networks_match(first_station, second_station):
            return False

        first_addresses = set(map(str.lower, first_station.street_address.all()))
        second_addresses = set(map(str.lower, second_station.street_address.all()))

        if not first_addresses and not second_addresses:
            return False

        if first_addresses and second_addresses:
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.05:
            return False

        return True

    return combine_stations_with_check(all_stations, check_same_address, [filter_out_non_networked, filter_out_unknown_network])

def combine_networked_stations_close_by(all_stations: list[Station]) -> list[Station]:
    def check_close_location(first_station: Station, second_station: Station) -> bool:
        if not station_networks_match(first_station, second_station):
            return False

        first_addresses = set(map(str.lower, first_station.street_address.all()))
        second_addresses = set(map(str.lower, second_station.street_address.all()))

        if first_addresses or second_addresses:
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.01:
            return False

        return True

    return combine_stations_with_check(all_stations, check_close_location, [filter_out_non_networked, filter_out_unknown_network])

def combine_non_networked_stations_at_same_address(all_stations: list[Station]) -> list[Station]:
    def check_same_address(first_station: Station, second_station: Station) -> bool:
        first_addresses = set(map(str.lower, first_station.street_address.all()))
        second_addresses = set(map(str.lower, second_station.street_address.all()))

        if not first_addresses and not second_addresses:
            return False

        if first_addresses and second_addresses:
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.1:
            return False

        return True

    return combine_stations_with_check(all_stations, check_same_address, [filter_out_networked])

def combine_non_networked_stations_close_by(all_stations: list[Station]) -> list[Station]:
    def check_non_networked_close_by(first_station: Station, second_station: Station) -> bool:
        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.01:
            return False

        return True

    return combine_stations_with_check(all_stations, check_non_networked_close_by, [filter_out_networked])

def combine_networked_stations_with_unknown_ones_near_by(all_stations: list[Station]) -> list[Station]:
    def check_unknown_networked_close_by(first_station: Station, second_station: Station) -> bool:
        if first_station.network is not None and second_station.network is not None:
            return False

        if first_station.network is None and second_station.network is None:
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.01:
            return False

        return True

    return combine_stations_with_check(all_stations, check_unknown_networked_close_by, [filter_out_non_networked])

def combine_non_networked_stations_with_unknown_ones_near_by(all_stations: list[Station]) -> list[Station]:
    def check_unknown_networked_close_by(first_station: Station, second_station: Station) -> bool:
        if first_station.network is not None and second_station.network is not None:
            return False

        if first_station.network != "NON_NETWORKED" and second_station.network != "NON_NETWORKED":
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.01:
            return False

        return True

    return combine_stations_with_check(all_stations, check_unknown_networked_close_by)


def station_networks_match(first_station: Station, second_station: Station) -> bool:
    if first_station.network is None or first_station.network == "NON_NETWORKED":
        return False

    if second_station.network is None or second_station.network == "NON_NETWORKED":
        return False

    return first_station.network == second_station.network

def combine_stations_with_check(all_stations: list[Station], check, pre_filters=[]) -> list[Station]:
    combined_stations = []

    stations_to_check = queue.Queue()
    remaining_stations = []

    for station in all_stations:
        selected_for_check = True

        for filter_fn in pre_filters:
            if not filter_fn(station):
                selected_for_check = False

                break

        if selected_for_check:
            stations_to_check.put(station)
            remaining_stations.append(station)
        else:
            combined_stations.append(station)

    while not stations_to_check.empty():
        first_station = stations_to_check.get()

        if first_station not in remaining_stations:
            stations_to_check.task_done()
            continue

        remaining_stations.remove(first_station)

        for second_station in remaining_stations[:]:
            if not check(first_station, second_station):
                continue

            combined_station = merge_stations(first_station, second_station)

            remaining_stations.remove(second_station)

            stations_to_check.put(combined_station)
            remaining_stations.append(combined_station)

            stations_to_check.task_done()

            break
        else:
            combined_stations.append(first_station)
            stations_to_check.task_done()

    return combined_stations


def combine_matched_stations_by_ids(all_stations: list[Station]) -> list[Station]:
    def osm_ids_match(first_station: Station, second_station: Station) -> bool:
        return set(first_station.osm_id.all()) & set(second_station.osm_id.all())

    def ocm_ids_match(first_station: Station, second_station: Station) -> bool:
        return set(first_station.ocm_id.all()) & set(second_station.ocm_id.all())

    def nrel_ids_match(first_station: Station, second_station: Station) -> bool:
        return set(first_station.nrel_id.all()) & set(second_station.nrel_id.all())

    def filter_missing_id(id_type: str):
        def filter_function(station: Station):
            attr = getattr(station, id_type)

            return attr.all()

        return filter_function

    all_stations = combine_stations_with_check(all_stations, osm_ids_match, [filter_missing_id("osm_id")])
    all_stations = combine_stations_with_check(all_stations, ocm_ids_match, [filter_missing_id("ocm_id")])
    all_stations = combine_stations_with_check(all_stations, nrel_ids_match, [filter_missing_id("nrel_id")])

    return all_stations


def combine_matched_networked_stations_by_network_ids(all_stations: list[Station]) -> list[Station]:
    def check_network_ids(first_station: Station, second_station: Station) -> bool:
        if not station_networks_match(first_station, second_station):
            return False

        if set(map(str.lower, first_station.network_id.all())) & set(map(str.lower, second_station.network_id.all())):
            return True

        return False

    def filter_missing_network_id(station: Station):
        return station.network_id.all()

    return combine_stations_with_check(all_stations, check_network_ids, [filter_out_non_networked, filter_out_unknown_network, filter_missing_network_id])


def combine_nrel_non_networked_with_unsupported_network_at_same_address(all_stations: list[Station]) -> list[Station]:
    def check_network_ids(first_station: Station, second_station: Station) -> bool:
        NREL_UNSUPPORTED_NETWORKS = [
            "AMP_UP",
            "ENEL_X",
            "EV_PASSPORT",
        ]

        if first_station.network != "NON_NETWORKED" and second_station.network != "NON_NETWORKED":
            return False

        if first_station.network == "NON_NETWORKED" and second_station.network == "NON_NETWORKED":
            return False

        if first_station.network not in NREL_UNSUPPORTED_NETWORKS and second_station.network not in NREL_UNSUPPORTED_NETWORKS:
            return False

        if not first_station.nrel_id.get() and second_station.nrel_id.get():
            return False

        first_addresses = set(map(str.lower, first_station.street_address.all()))
        second_addresses = set(map(str.lower, second_station.street_address.all()))

        if not first_addresses or not second_addresses:
            return False

        if not (first_addresses & second_addresses):
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.5:
            return False

        # Force the network onto the station marked as non-networked
        if first_station.network == "NON_NETWORKED":
            first_station.network = second_station.network
        elif second_station.network == "NON_NETWORKED":
            second_station.network = first_station.network

        return True

    return combine_stations_with_check(all_stations, check_network_ids)


def combine_stations(all_stations: list[Station]) -> list[Station]:
    all_stations = combine_matched_stations_by_ids(all_stations)
    all_stations = combine_matched_networked_stations_by_network_ids(all_stations)
    all_stations = combine_tesla_superchargers(all_stations)
    all_stations = combine_nrel_non_networked_with_unsupported_network_at_same_address(all_stations)

    all_stations = combine_networked_stations_at_same_address(all_stations)
    all_stations = combine_networked_stations_near_known_address(all_stations)
    all_stations = combine_networked_stations_close_by(all_stations)

    all_stations = combine_non_networked_stations_at_same_address(all_stations)
    all_stations = combine_non_networked_stations_close_by(all_stations)
    all_stations = combine_networked_stations_with_unknown_ones_near_by(all_stations)
    all_stations = combine_non_networked_stations_with_unknown_ones_near_by(all_stations)

    return all_stations


def sourced_attribute_to_geojson_property(sourced_attribute: SourcedAttribute) -> list:
    property_values = []

    for sourced_value in sorted(sourced_attribute.values, key=lambda v: (-v.source.quality.value, v.value, v.source.system)):
        source = sourced_value.source

        property_value = {
            "value": sourced_value.value,
            "source": {
                "name": source.system,
                "quality": source.quality.name,
            }
        }

        property_values.append(property_value)

    return property_values


def addresses_from_station(station: Station) -> list:
    from operator import attrgetter

    addresses = []

    sourced_information: dict[SourceLocation, ] = defaultdict(dict)

    for street_address in sorted(station.street_address.values, key=attrgetter("value")):
        sourced_information[street_address.source]["street_address"] = street_address.value

    for city in sorted(station.city.values, key=attrgetter("value")):
        sourced_information[city.source]["city"] = city.value

    for state in sorted(station.state.values, key=attrgetter("value")):
        sourced_information[state.source]["state"] = state.value

    for zip_code in sorted(station.zip_code.values, key=attrgetter("value")):
        sourced_information[zip_code.source]["zip_code"] = zip_code.value

    for source, address in sourced_information.items():
        addresses.append({
            "address": address,
            "source": {
                "name": source.system,
                "quality": source.quality.name,
            }
        })

    return sorted(addresses, key=lambda a: (-SourceLocationQualityScore[a["source"]["quality"]].value, -len(a["address"]), a["source"]["name"]))


def parse_stations(raw_contents):
    stations = []

    for raw_station in raw_contents:
        station = Station()

        source_data = SourceLocation(
            system=raw_station["source"]["system"],
            quality=SourceLocationQualityScore[raw_station["source"]["quality"]],
        )

        if station_name := raw_station.get("name"):
            station.name.set(SourcedValue(source_data, station_name))

        station_location = Location(
            latitude=float(raw_station["location"]["latitude"]),
            longitude=float(raw_station["location"]["longitude"]),
        )
        station.location.set(SourcedValue(source_data, station_location))

        if station_network_id := raw_station.get("network_id"):
            station.network_id.set(SourcedValue(source_data, str(station_network_id)))

        station.network = raw_station["network"]

        if station.network == "":
            station.network = None

        if raw_address := raw_station.get("address"):
            if street_address := raw_address.get("street_address"):
                if street_address.strip():
                    station.street_address.set(SourcedValue(source_data, normalize_address_street_address(street_address)))

            if city := raw_address.get("city"):
                station.city.set(SourcedValue(source_data, city))

            if state := raw_address.get("state"):
                station.state.set(SourcedValue(source_data, state))

            if zip_code := raw_address.get("zip_code"):
                station.zip_code.set(SourcedValue(source_data, zip_code))

        for reference in raw_station.get("references", []):
            if reference["system"] == "ALTERNATIVE_FUEL_DATA_CENTER":
                station.nrel_id.set(SourcedValue(source_data, int(reference["identifier"])))

            if reference["system"] == "OPEN_STREET_MAP":
                station.osm_id.set(SourcedValue(source_data, reference["identifier"]))

            if reference["system"] == "OPEN_CHARGE_MAP":
                station.ocm_id.set(SourcedValue(source_data, reference["identifier"]))

        charging_points = []

        for raw_point in raw_station.get("charging_points", []):
            charging_point = ChargingPoint()

            if charger_name := raw_point.get("name"):
                charging_point.name = charger_name

            if raw_location := raw_point.get("location"):
                charger_location = Location(
                    latitude=float(raw_location["latitude"]),
                    longitude=float(raw_location["longitude"]),
                )
                charging_point.location.set(SourcedValue(source_data, charger_location))

            if point_network_id := raw_point.get("network_id"):
                charging_point.network_id.set(SourcedValue(source_data, point_network_id))

            for reference in raw_point.get("references", []):
                if reference["system"] == "ALTERNATIVE_FUEL_DATA_CENTER":
                    charging_point.nrel_id.set(SourcedValue(source_data, int(reference["identifier"])))

                if reference["system"] == "OPEN_STREET_MAP":
                    charging_point.osm_id.set(SourcedValue(source_data, reference["identifier"]))

                if reference["system"] == "OPEN_CHARGE_MAP":
                    charging_point.ocm_id.set(SourcedValue(source_data, reference["identifier"]))

            groups = []

            for raw_evse in raw_point.get("evses", []):
                charging_point_group = ChargingPortGroup(
                    network_id=raw_evse.get("network_id"),
                )

                ports = []

                for raw_port in raw_evse.get("plugs", []):
                    if plug := raw_port["plug"]:
                        if plug in ["J1772_CABLE", "J1722_CABLE"]:
                            plug = "J1772"

                        port = ChargingPort(
                            plug=PlugType[plug],
                        )

                        ports.append(port)

                charging_point_group.charging_ports = ports

                groups.append(charging_point_group)

            charging_point.charging_port_groups = groups

            charging_points.append(charging_point)

        station.charging_points = charging_points

        stations.append(station)

    return stations

scraped_data = pathlib.Path("./scraped_data/")

stations = []

data_file_map = {}

for data_file in scraped_data.glob("*"):
    if not data_file.is_file():
        data_file_map[data_file.name] = "dir"
    else:
        data_file_name, _ = data_file.name.split(".", 1)
        if data_file_name not in data_file_map:
            data_file_map[data_file_name] = "file"

for source_name, data_type in data_file_map.items():
    if data_type == "file":
        data_file = scraped_data / f"{source_name}.json"

        with data_file.open() as fh:
            try:
                contents = json.load(fh)
            except:
                contents = []

        parsed_stations = parse_stations(contents)

        stations.extend(parsed_stations)
    elif data_type == "dir":
        source_dir = scraped_data / source_name

        data_file_names = sorted([data_file.name for data_file in source_dir.glob("*.json")], reverse=True)
        for data_file_name in data_file_names:
            data_file = source_dir / data_file_name

            with data_file.open() as fh:
                try:
                    contents = json.load(fh)
                except:
                    contents = []

            if not contents:
                continue

            parsed_stations = parse_stations(contents)

            stations.extend(parsed_stations)

            break

combined_data = combine_stations(stations)

combined_data = sorted(combined_data, key=lambda x: (x.name.get() or '', x.network or '', x.location.get().longitude))

station_features = geojson.FeatureCollection([])
non_reconciled_station_features = geojson.FeatureCollection([])

for station in combined_data:
    station_location = station.location.get()
    station_point = geojson.Point(
        coordinates=(station_location.longitude, station_location.latitude),
    )

    station_properties = {}

    if station.name.get():
        station_properties["name"] = sourced_attribute_to_geojson_property(station.name)
    if station.network:
        station_properties["network"] = station.network
    if station.network_id.get():
        station_properties["network_id"] = sourced_attribute_to_geojson_property(station.network_id)

    if station_addresses := addresses_from_station(station):
        station_properties["address"] = station_addresses

    references = []

    for osm_id in station.osm_id.all():
        osm_type, ref = osm_id.split(":")

        references.append({
            "name": "OPEN_STREET_MAP",
            "url": f"https://www.openstreetmap.org/{osm_type}/{ref}",
        })

    for ocm_id in station.ocm_id.all():
        references.append({
            "name": "OPEN_CHARGE_MAP",
            "url": f"https://openchargemap.org/site/poi/details/{ocm_id}",
        })

    for nrel_id in station.nrel_id.all():
        references.append({
            "name": "ALTERNATIVE_FUELS_DATA_CENTER",
            "url": f"https://afdc.energy.gov/stations#/station/{nrel_id}",
        })

    if references:
        station_properties["references"] = sorted(references, key=lambda r: (r["name"], r["url"]))

    if station.charging_points:
        charging_points = []

        for station_charging_point in sorted(station.charging_points, key=lambda c: (c.name, (c.network_id.get() or ""))):
            charging_point = {
                "charging_groups": [],
                "name": station_charging_point.name,
            }

            if station_charging_point.network_id.get():
                charging_point["network_id"] = sourced_attribute_to_geojson_property(station_charging_point.network_id)

            if station_charging_point.ocm_id.get():
                charging_point["ocm_id"] = sourced_attribute_to_geojson_property(station_charging_point.ocm_id)

            if station_charging_point.osm_id.get():
                charging_point["osm_id"] = sourced_attribute_to_geojson_property(station_charging_point.osm_id)

            if station_charging_point.nrel_id.get():
                charging_point["nrel_id"] = sourced_attribute_to_geojson_property(station_charging_point.nrel_id)

            for station_charging_group in station_charging_point.charging_port_groups:
                charging_group = {
                    "ports": [],
                }

                if station_charging_group.network_id:
                    charging_group["network_id"] = station_charging_group.network_id

                for station_charging_port in station_charging_group.charging_ports:
                    charging_port = {
                        "plug_type": station_charging_port.plug.name,
                    }

                    charging_group["ports"].append(charging_port)

                charging_point["charging_groups"].append(charging_group)

            charging_points.append(charging_point)

        station_properties["charging_points"] = charging_points

        charging_point_coordinates = set()

        for charging_point in station.charging_points:
            point_location = charging_point.location.get()

            if not point_location:
                continue

            charging_point_coordinates.add((point_location.longitude, point_location.latitude))

        if len(charging_point_coordinates) > 1:
            station_point = geojson.MultiPoint(
                coordinates=list(sorted(charging_point_coordinates)),
            )
        elif len(charging_point_coordinates) == 1:
            station_point = geojson.Point(
                coordinates=charging_point_coordinates.pop(),
            )

    station_feature = geojson.Feature(
        geometry=station_point,
        properties=station_properties,
    )
    station_features["features"].append(station_feature)

    id_count = 0

    if station.nrel_id.get():
        id_count += 1

    if station.osm_id.get():
        id_count += 1

    if station.ocm_id.get():
        id_count += 1

    if station.network_id.get():
        id_count += 1

    if id_count <= 1:
        non_reconciled_station_features["features"].append(station_feature)

with open("stations.geojson", "w") as stations_fh:
    geojson.dump(station_features, stations_fh, indent=4)

with open("non-reconciled-stations.geojson", "w") as stations_fh:
    geojson.dump(non_reconciled_station_features, stations_fh, indent=4)

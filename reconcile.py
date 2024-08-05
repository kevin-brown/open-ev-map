from collections import defaultdict
from dataclasses import dataclass
from geopy import distance
from typing import NamedTuple, Self, reveal_type
import dataclasses
import enum
import geojson
import json
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


class SourceLocation(enum.Enum):
    ALTERNATIVE_FUELS_DATA_CENTER = enum.auto()
    OPEN_CHARGE_MAP = enum.auto()
    OPEN_STREET_MAP = enum.auto()


class SourceData(NamedTuple):
    location: SourceLocation
    reference: str


class SourcedValue[T](NamedTuple):
    source: SourceData
    value: T


class SourcedAttribute[T]:
    values: set[SourcedValue[T]]
    multiple: bool

    def __init__(self, multiple=False):
        self.values = set()
        self.multiple = multiple

    def set(self, value: SourcedValue[T]):
        if not value.value:
            return

        self.values.add(value)

    def get(self) -> T:
        if self.multiple:
            return sorted(set(self.all()))

        if not self.values:
            return None

        first_value = next(iter(self.values)).value

        if not isinstance(first_value, str):
            return first_value

        raw_values = sorted(set(self.all()))

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

    osm_id: int = None
    nrel_id: int = None
    ocm_id: int = None

    network_id: str = ""


@dataclass
class Station:
    charging_points: list[ChargingPoint] = dataclasses.field(default_factory=list)

    name: SourcedAttribute[str] = dataclasses.field(default_factory=SourcedAttribute)
    network: ChargingNetwork = None

    location: SourcedAttribute[Location] = dataclasses.field(default_factory=SourcedAttribute)
    street_address: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""

    osm_id: int = None
    nrel_id: SourcedAttribute[list[int]] = dataclasses.field(default_factory=lambda: SourcedAttribute(multiple=True))
    ocm_id: int = None

    network_id: str = ""


def get_station_distance(first_station: Station, second_station: Station) -> distance.Distance:
    first_locations = first_station.location.all()
    second_locations = second_station.location.all()

    lowest_station_distance = 2 ** 8

    for first_location in first_locations:
        for second_location in second_locations:
            first_coordinates = first_location.coordinates
            second_coordinates = second_location.coordinates

            station_distance = distance.great_circle(first_coordinates, second_coordinates)

            if station_distance < lowest_station_distance:
                lowest_station_distance = station_distance

    return station_distance


def merge_stations(first_station: Station, second_station: Station) -> Station:
    combined_station = dataclasses.replace(first_station)

    CLONED_ATTRS = ['osm_id', 'ocm_id', 'street_address', 'city', 'state', 'zip_code']

    for attr in CLONED_ATTRS:
        second_value = getattr(second_station, attr)
        if second_value:
            setattr(combined_station, attr, second_value)

    combined_station.charging_points = [*first_station.charging_points, *second_station.charging_points]

    if first_station.network_id and not second_station.network_id:
        combined_station.network_id = first_station.network_id
    elif not first_station.network_id and second_station.network_id:
        combined_station.network_id = second_station.network_id
    elif first_station.network_id and second_station.network_id:
        combined_station.network_id = f"{first_station.network_id};{second_station.network_id}"

    combined_station.name.extend(first_station.name)
    combined_station.name.extend(second_station.name)

    combined_station.nrel_id.extend(first_station.nrel_id)
    combined_station.nrel_id.extend(second_station.nrel_id)

    combined_station.location.extend(first_station.location)
    combined_station.location.extend(second_station.location)

    return combined_station


def nrel_group_chargepoint(nrel_stations: list[Station]) -> list[Station]:
    cleaned_stations = []

    for station in nrel_stations:
        if station.network != ChargingNetwork.CHARGEPOINT:
            cleaned_stations.append(station)
            continue

        if getattr(station, "matched_nrel_cp", False):
            continue

        for other_station in nrel_stations:
            if getattr(other_station, "matched_nrel_cp", False):
                continue

            if other_station.network != ChargingNetwork.CHARGEPOINT:
                continue

            if station == other_station:
                continue

            if station.street_address.lower() != other_station.street_address.lower():
                continue

            station_distance = get_station_distance(station, other_station)

            if station_distance.miles > 0.1:
                continue

            combined_station = merge_stations(station, other_station)

            station.matched_nrel_cp = True
            other_station.matched_nrel_cp = True

            station = combined_station

        cleaned_stations.append(station)

    return cleaned_stations


def normalize_address_street_address(street_address: str) -> str:
    STREET_TYPE_MAP = {
        "ave": "Avenue",
        "blvd": "Boulevard",
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

        if is_extension:
            address_parts.append("Extension")

        street_address = " ".join(address_parts)

    if street_address.endswith(".") or street_address.endswith(","):
        street_address = street_address[:-1]

    return street_address


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
        "LOOP": ChargingNetwork.LOOP,
        "NOODOE": ChargingNetwork.NOODOE,
        "Non-Networked": ChargingNetwork.NON_NETWORKED,
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
            network=NREL_NETWORK_MAP[nrel_station["ev_network"]],

            street_address=normalize_address_street_address(nrel_station["street_address"]),
            city=nrel_station["city"],
            state=nrel_station["state"],
            zip_code=nrel_station["zip"],
        )

        station.name.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), nrel_station["station_name"]))
        station.nrel_id.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), nrel_station["id"]))
        station_location = Location(latitude=nrel_station["latitude"], longitude=nrel_station["longitude"])
        station.location.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), station_location))

        charging_points = []

        if "ev_network_ids" in nrel_station:
            station.network_id = nrel_station["ev_network_ids"].get("station", [None])[0]

            charging_port_groups = []

            if station.network not in [ChargingNetwork.TESLA_SUPERCHARGER, ChargingNetwork.TESLA_DESTINATION]:
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
                    nrel_id=nrel_station["id"],
                    name=station.name.get(),
                    charging_port_groups=charging_port_groups,
                )
                charging_point_location = Location(latitude=nrel_station["latitude"], longitude=nrel_station["longitude"])
                charging_point.location.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), charging_point_location))

                charging_points.append(charging_point)

        station.charging_points = charging_points

        stations.append(station)

    stations = nrel_group_chargepoint(stations)

    return stations


def osm_parse_charging_station(osm_element) -> Station:
    OSM_NETWORK_NAME_MAP = {
        "AmpUp": ChargingNetwork.AMPUP,
        "Autel": ChargingNetwork.AUTEL,
        "Blink": ChargingNetwork.BLINK,
        "ChargePoint": ChargingNetwork.CHARGEPOINT,
        "Electrify America": ChargingNetwork.ELECTRIFY_AMERICA,
        "Enel X": ChargingNetwork.ENEL_X,
        "EV Connect": ChargingNetwork.EV_CONNECT,
        "EVgo": ChargingNetwork.EVGO,
        "Electric Era": ChargingNetwork.ELECTRIC_ERA,
        "EVPassport": ChargingNetwork.EVPASSPORT,
        "Greenspot": ChargingNetwork.GREENSPOT,
        "Loop": ChargingNetwork.LOOP,
        "Tesla": None, # Ambiguous
        "Tesla, Inc.": None, # Ambiguous
        "Tesla Supercharger": ChargingNetwork.TESLA_SUPERCHARGER,
        "Volta": ChargingNetwork.VOLTA,
    }

    OSM_NETWORK_WIKIDATA_MAP = {
        # Tesla, Inc., currently ambiguous
        "Q478214": None,

        "Q17089620": ChargingNetwork.TESLA_SUPERCHARGER,
        "Q5176149": ChargingNetwork.CHARGEPOINT,
        "Q59773555": ChargingNetwork.ELECTRIFY_AMERICA,
        "Q61803820": ChargingNetwork.EVGO,
        "Q62065645": ChargingNetwork.BLINK,
        "Q109307156": ChargingNetwork.VOLTA,
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

        "AmpUp": ChargingNetwork.AMPUP,
        "ChargePoint": ChargingNetwork.CHARGEPOINT,
        "Shell Recharge Solutions": ChargingNetwork.SHELL_RECHARGE,
    }

    OSM_OPERATOR_WIKIDATA_NETWORK_MAP = {
        # ABB Group
        "Q52825": None,
        # Tesla, Inc., currently ambiguous
        "Q478214": None,
        # AeroVironment
        "Q919300": None,
        # NRG Energy, most likely EVgo
        "Q6955139": ChargingNetwork.EVGO,

        "Q5176149": ChargingNetwork.CHARGEPOINT,
        "Q59773555": ChargingNetwork.ELECTRIFY_AMERICA,
        "Q61803820": ChargingNetwork.EVGO,
        "Q62065645": ChargingNetwork.BLINK,
        "Q105883058": ChargingNetwork.SHELL_RECHARGE,
        "Q109307156": ChargingNetwork.VOLTA,
    }

    OSM_BRAND_NAME_NETWORK_MAP = {
        "ABB": None, # Non-networked
        "ChargePoint": ChargingNetwork.CHARGEPOINT,
        "Enel": ChargingNetwork.ENEL_X,
        "Tesla, Inc.": None, # Ambiguous
        "Tesla Supercharger": ChargingNetwork.TESLA_SUPERCHARGER,
        "Volta": ChargingNetwork.VOLTA,
        "WattZilla": None, # Non-networked
    }

    OSM_BRAND_WIKIDATA_NETWORK_MAP = {
        # ABB Group
        "Q52825": None,
        # Tesla, Inc., currently ambiguous
        "Q478214": None,
        # AeroVironment
        "Q919300": None,

        "Q5176149": ChargingNetwork.CHARGEPOINT,
        "Q17089620": ChargingNetwork.TESLA_SUPERCHARGER,
        "Q61803820": ChargingNetwork.EVGO,
    }

    station = Station(
        osm_id=osm_element["id"],
    )

    if osm_element["type"] == "node":
        station_location = Location(latitude=osm_element["lat"], longitude=osm_element["lon"])
        station.location.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), station_location))

    if osm_element["type"] in ["way", "relation"]:
        station_location = Location(
            latitude=(osm_element["bounds"]["minlat"] + osm_element["bounds"]["maxlat"]) / 2,
            longitude=(osm_element["bounds"]["minlon"] + osm_element["bounds"]["maxlon"]) / 2,
        )
        station.location.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), station_location))

    tags = osm_element["tags"]

    if "name" in tags:
        station_name = tags["name"]

        if station_name.lower() not in ["chargepoint", "tesla supercharger", "tesla supercharging station", "tesla destination charger"]:
            station.name.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), station_name))

    if "no:network" in tags:
        station.network = ChargingNetwork.NON_NETWORKED

    if station.network is None:
        if station.network is None and "network:wikidata" in tags:
            station.network = OSM_NETWORK_WIKIDATA_MAP[tags["network:wikidata"]]

        if station.network is None and "network" in tags:
            station.network = OSM_NETWORK_NAME_MAP[tags["network"]]

        if station.network is None and "operator:wikidata" in tags:
            station.network = OSM_OPERATOR_WIKIDATA_NETWORK_MAP[tags["operator:wikidata"]]

        if station.network is None and "operator" in tags:
            station.network = OSM_OPERATOR_NAME_MAP[tags["operator"]]

        if station.network is None and "brand:wikidata" in tags:
            station.network = OSM_BRAND_WIKIDATA_NETWORK_MAP[tags["brand:wikidata"]]

        if station.network is None and "brand" in tags:
            station.network = OSM_BRAND_NAME_NETWORK_MAP[tags["brand"]]

        if station.network is None and "name" in tags:
            station_name = tags["name"].lower()

            if "supercharger" in station_name or "super charger" in station_name:
                station.network = ChargingNetwork.TESLA_SUPERCHARGER

            if station.network is None and "tesla" in station_name:
                if "destination" in station_name:
                    station.network = ChargingNetwork.TESLA_DESTINATION

    return station


def osm_parse_charging_station_bounds(osm_element) -> shapely.Polygon:
    return shapely.box(
        xmin=osm_element["bounds"]["minlat"],
        xmax=osm_element["bounds"]["maxlat"],
        ymin=osm_element["bounds"]["minlon"],
        ymax=osm_element["bounds"]["maxlon"],
    )


def osm_parse_charging_point(osm_element) -> ChargingPoint:
    OSM_SOCKETS_TO_PLUGS = {
        "type1": PlugType.J1772_SOCKET,
        "type1_cable": PlugType.J1772,
        "type1_combo": PlugType.J1772_COMBO,
        "chademo": PlugType.CHADEMO,
        "tesla_destination": PlugType.NACS,
        "tesla_supercharger": PlugType.NACS,
    }

    osm_tags = osm_element["tags"]

    charging_point = ChargingPoint(
        osm_id=osm_element["id"],
    )

    charging_point_location = Location(latitude=osm_element["lat"], longitude=osm_element["lon"])
    charging_point.location.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), charging_point_location))

    socket_counts: dict[str, int] = {}

    for tag_name, tag_value in osm_tags.items():
        if not tag_name.startswith("socket:"):
            continue

        if tag_name.count(":") > 1:
            continue

        _, socket_type = tag_name.split(":")

        socket_counts[socket_type] = int(tag_value)

    charging_point_capacity = int(osm_tags.get("capacity", 1))
    charging_port_groups = []

    if sum(socket_counts.values()) == charging_point_capacity:
        for socket_type, socket_count in socket_counts.items():
            for _ in range(socket_count):
                charging_port_group = ChargingPortGroup(
                    charging_ports=[ChargingPort(plug=OSM_SOCKETS_TO_PLUGS[socket_type])]
                )
                charging_port_groups.append(charging_port_group)
    elif charging_point_capacity == 1 and socket_counts:
        charging_port_group = ChargingPortGroup()

        for socket_type in socket_counts.keys():
            charging_port = ChargingPort(plug=OSM_SOCKETS_TO_PLUGS[socket_type])
            charging_port_group.charging_ports.append(charging_port)

        charging_port_groups.append(charging_port_group)

    charging_point.charging_port_groups = charging_port_groups

    return charging_point


def normalize_osm_data(osm_raw_data) -> list[Station]:
    stations: dict[int, Station] = {}

    charge_points: dict[int, ChargingPoint] = {}
    station_boundaries: dict[int, shapely.Polygon] = {}

    for osm_element in osm_raw_data["elements"]:
        if osm_element["tags"].get("amenity") != "charging_station":
            continue

        stations[osm_element["id"]] = osm_parse_charging_station(osm_element)

        if osm_element["type"] == "way":
            station_boundaries[osm_element["id"]] = osm_parse_charging_station_bounds(osm_element)

    for osm_element in osm_raw_data["elements"]:
        if osm_element["tags"].get("man_made") != "charge_point":
            continue

        charge_point = osm_parse_charging_point(osm_element)

        charge_point_associated = False

        for station_id, station_boundary in station_boundaries.items():
            if shapely.contains(station_boundary, charge_point.location.get().point):
                stations[station_id].charging_points.append(charge_point)

                charge_point_associated = True

                break

        if not charge_point_associated:
            charge_points[osm_element["id"]] = charge_point

    for osm_element in osm_raw_data["elements"]:
        if osm_element["tags"].get("amenity") != "charging_station":
            continue

        if osm_element["type"] != "relation":
            continue

        for osm_member in osm_element["members"]:
            if osm_member["ref"] in charge_points:
                stations[osm_element["id"]].charging_points.append(charge_points[osm_member["ref"]])
                del charge_points[osm_member["ref"]]

    charge_points_found = []

    for charge_point_id, charge_point in charge_points.items():
        for station_id, station in stations.items():
            charge_point_distance_to_station = get_station_distance(station, charge_point)

            if charge_point_distance_to_station.miles > 0.05:
                continue

            station.charging_points.append(charge_point)

            charge_points_found.append(charge_point_id)

            break

    for charge_point_id in charge_points_found:
        del charge_points[charge_point_id]

    return stations.values()


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

        6: None, # Nissan
        11: None, # AFDC Import
        26: None, # AeroVironment
        31: None, # Clipper Creek
        39: None, # SemaConnect
        42: None, # Eaton
        45: None, # Private Owner
        3293: None, # Revolta Egypt
        3460: None, # PEA Volta
        3493: None, # SWTCH
        3620: None, # Livingston Charge Port / solution.energy
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
        station = Station(
            ocm_id=ocm_station["ID"],
        )
        ocm_address = ocm_station["AddressInfo"]

        if "Title" in ocm_address:
            station_name = ocm_address["Title"]

            station.name.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), station_name))

        station_location = Location(latitude=ocm_address["Latitude"], longitude=ocm_address["Longitude"])
        station.location.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), station_location))

        if "OperatorInfo" in ocm_station:
            ocm_operator = ocm_station["OperatorInfo"]
            station.network = OCM_OPERATOR_TO_NETWORK_MAP[ocm_operator["ID"]]

        station.street_address = normalize_address_street_address(ocm_address["AddressLine1"])
        station.city = ocm_address["Town"]
        station.state = ocm_address.get("StateOrProvince")
        station.zip_code = ocm_address.get("Postcode")

        if station.state and len(station.state) > 2 and ocm_address["CountryID"] == 2:
            station.state = OCM_LONG_STATE_TO_SHORT_MAP[station.state.lower()]

        if station.zip_code and len(station.zip_code) < 5 and ocm_address["CountryID"] == 2:
            station.zip_code = station.zip_code.rjust(5, "0")

        if ocm_station["DataProviderID"] == 2:
            station.nrel_id.set(SourcedValue(SourceData(SourceLocation.OPEN_CHARGE_MAP, ocm_station["ID"]), int(ocm_station["DataProvidersReference"])))

        if station.network == ChargingNetwork.TESLA_SUPERCHARGER:
            if ocm_station["Connections"][0]["CurrentTypeID"] == 10:
                station.network = ChargingNetwork.TESLA_DESTINATION

        stations.append(station)

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
        if getattr(first_station, "matched_tesla", False):
            continue

        for second_station in tesla_stations:
            if first_station == second_station:
                continue

            if getattr(second_station, "matched_tesla", False):
                continue

            station_distance = get_station_distance(first_station, second_station)

            if station_distance.miles > 0.1:
                continue

            combined_station = merge_stations(first_station, second_station)

            first_station.matched_tesla = True
            second_station.matched_tesla = True

            first_station = combined_station

        combined_stations.append(first_station)

    return combined_stations


def combine_networked_stations(all_stations: list[Station]) -> list[Station]:
    all_stations = combine_tesla_superchargers(all_stations)
    combined_stations = []

    for first_station in all_stations:
        if getattr(first_station, "matched_network", False):
            continue

        for second_station in all_stations:
            if getattr(second_station, "matched_network", False):
                continue

            if first_station == second_station:
                continue

            if first_station.network is None or first_station.network is ChargingNetwork.NON_NETWORKED:
                continue

            if second_station.network is None or second_station.network is ChargingNetwork.NON_NETWORKED:
                continue

            if first_station.network != second_station.network:
                continue

            station_distance = get_station_distance(first_station, second_station)

            if station_distance.miles > 0.05:
                continue

            combined_station = merge_stations(first_station, second_station)

            first_station.matched_network = True
            second_station.matched_network = True

            first_station = combined_station

        combined_stations.append(first_station)

    return combined_stations


def combine_matched_stations_by_ids(all_stations: list[Station]) -> list[Station]:
    combined_stations = []

    for station in all_stations:
        if getattr(station, "matched_ids", False):
            continue

        for other_station in all_stations:
            if station == other_station:
                continue

            if getattr(other_station, "matched_ids", False):
                continue

            matched = False

            if station.osm_id and other_station.osm_id and station.osm_id == other_station.osm_id:
                matched = True

            if station.ocm_id and other_station.ocm_id and station.ocm_id == other_station.ocm_id:
                matched = True

            if station.nrel_id.get() and other_station.nrel_id.get():
                if set(station.nrel_id.get()) & set(other_station.nrel_id.get()):
                    matched = True

            if matched:
                combined_station = merge_stations(station, other_station)

                station.matched_ids = True
                other_station.matched_ids = True

                station = combined_station

        combined_stations.append(station)

    return combined_stations


def combine_stations(all_stations: list[Station]) -> list[Station]:
    all_stations = combine_matched_stations_by_ids(all_stations)

    all_stations = combine_networked_stations(all_stations)

    return all_stations


with open("nrel.json", "r") as nrel_fh:
    nrel_raw_data = json.load(nrel_fh)

with open("osm.json", "r") as osm_fh:
    osm_raw_data = json.load(osm_fh)

with open("ocm.json", "r") as ocm_fh:
    ocm_raw_data = json.load(ocm_fh)

nrel_data = normalize_nrel_data(nrel_raw_data)
osm_data = normalize_osm_data(osm_raw_data)
ocm_data = normalize_ocm_data(ocm_raw_data)

combined_data = combine_stations([*nrel_data, *osm_data, *ocm_data])

combined_data = sorted(combined_data, key=lambda x: x.name.get() or '')

station_features = geojson.FeatureCollection([])
non_reconciled_station_features = geojson.FeatureCollection([])

for station in combined_data:
    station_location = station.location.get()
    station_point = geojson.Point(
        coordinates=(station_location.longitude, station_location.latitude),
    )

    station_properties = {}

    if station.name.get():
        station_properties["name"] = station.name.get()
    if station.network:
        station_properties["network"] = station.network.name
    if station.osm_id:
        station_properties["osm_id"] = station.osm_id
    if station.nrel_id.get():
        station_properties["nrel_id"] = station.nrel_id.get()
    if station.ocm_id:
        station_properties["ocm_id"] = station.ocm_id
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

    if station.charging_points:
        station_properties["charging_points:count"] = len(station.charging_points)
        station_properties["charging_points:capacity"] = ";".join(str(len(charging_point.charging_port_groups)) for charging_point in station.charging_points)
        station_properties["charging_points:plugs_count"] = ";".join(str(sum(len(port_groups.charging_ports) for port_groups in charging_point.charging_port_groups)) for charging_point in station.charging_points)

        plug_types = set()

        for charging_point in station.charging_points:
            for charging_port_group in charging_point.charging_port_groups:
                for charging_port in charging_port_group.charging_ports:
                    plug_types.add(charging_port.plug.name)

        station_properties["charging_points:plugs_type"] = ";".join(sorted(plug_types))

        charging_point_coordinates = [
            (charging_point.location.get().longitude, charging_point.location.get().latitude)
            for charging_point in station.charging_points
        ]
        station_point = geojson.MultiPoint(
            coordinates=charging_point_coordinates,
        )

    station_feature = geojson.Feature(
        geometry=station_point,
        properties=station_properties,
    )
    station_features["features"].append(station_feature)

    if not station.nrel_id.get() and station.osm_id and station.network is not ChargingNetwork.NON_NETWORKED:
        non_reconciled_station_features["features"].append(station_feature)

with open("stations.geojson", "w") as stations_fh:
    geojson.dump(station_features, stations_fh, indent=4)

with open("non-reconciled-stations.geojson", "w") as stations_fh:
    geojson.dump(non_reconciled_station_features, stations_fh, indent=4)

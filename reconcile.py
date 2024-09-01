from collections import defaultdict
from dataclasses import dataclass
from geopy import distance
from typing import NamedTuple, Optional, Self
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
    ALTERNATIVE_FUELS_DATA_CENTER = 10
    OPEN_CHARGE_MAP = 20
    OPEN_STREET_MAP = 40
    SUPERCHARGE = 30


class SourceLocation(enum.Enum):
    ALTERNATIVE_FUELS_DATA_CENTER = enum.auto()
    OPEN_CHARGE_MAP = enum.auto()
    OPEN_STREET_MAP = enum.auto()
    SUPERCHARGE = enum.auto()


class SourceData(NamedTuple):
    location: SourceLocation
    reference: str

    @property
    def url(self):
        if self.location == SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER:
            return f"https://afdc.energy.gov/stations#/station/{self.reference}"

        if self.location == SourceLocation.OPEN_CHARGE_MAP:
            return f"https://openchargemap.org/site/poi/details/{self.reference}"

        if self.location == SourceLocation.OPEN_STREET_MAP:
            return f"https://www.openstreetmap.org/node/{self.reference}"

        if self.location == SourceLocation.SUPERCHARGE:
            return f"https://supercharge.info/map?siteID={self.reference}"


class SourcedValue[T](NamedTuple):
    source: SourceData
    value: T

    def __repr__(self):
        return f"<SourcedValue({self.source.location!r}, {self.value!r})>"


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
            return None

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

    if not first_network_ids and not second_network_ids:
        if len(first_points) != len(second_points):
            return [*first_points, *second_points]

        return first_points

    network_ids_to_charging_points = defaultdict(list)

    for charging_point in [*first_points, *second_points]:
        network_ids_to_charging_points[charging_point.network_id.get()].append(charging_point)

    combined_points = []

    for network_id, charging_points in network_ids_to_charging_points.items():
        if not network_id:
            combined_points.extend(charging_points)

            continue

        combined_point = charging_points[0]

        if len(charging_points) > 1:
            for charging_point in charging_points:
                combined_point = merge_charging_points(combined_point, charging_point)

        combined_points.append(combined_point)

    return combined_points


def merge_charging_points(first_point: ChargingPoint, second_point: ChargingPoint) -> ChargingPoint:
    combined_charging_point = ChargingPoint()

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

    combined_charging_point.charging_port_groups = first_point.charging_port_groups

    return combined_charging_point


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

            if not (set(map(str.lower, station.street_address.all())) & set(map(str.lower, other_station.street_address.all()))):
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
        )

        station.name.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), nrel_station["station_name"]))
        station.nrel_id.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), nrel_station["id"]))
        station_location = Location(latitude=nrel_station["latitude"], longitude=nrel_station["longitude"])
        station.location.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), station_location))

        station_zip_code = nrel_station["zip"]
        if station_zip_code and len(station_zip_code) < 5:
            station_zip_code = station_zip_code.rjust(5, "0")

        station.street_address.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), normalize_address_street_address(nrel_station["street_address"])))
        station.city.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), nrel_station["city"]))
        station.state.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), nrel_station["state"]))
        station.zip_code.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), station_zip_code))

        station.network_id.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), nrel_station.get("ev_network_ids", {}).get("station", [None])[0]))

        station.charging_points = nrel_parse_charging_points_default(nrel_station, station)

        stations.append(station)

    stations = nrel_group_chargepoint(stations)

    return stations


def nrel_parse_charging_points_default(nrel_station, station: Station) -> list[ChargingPoint]:
    NREL_PLUG_MAP = {
        "CHADEMO": PlugType.CHADEMO,
        "TESLA": PlugType.NACS,

        "J1772": PlugType.J1772,
        "J1772COMBO": PlugType.J1772_COMBO,
    }

    charging_points = []

    if "ev_network_ids" not in nrel_station:
        return []

    charging_port_groups = []

    if station.network in [ChargingNetwork.TESLA_SUPERCHARGER, ChargingNetwork.TESLA_DESTINATION]:
        return []

    for nrel_post_id in nrel_station["ev_network_ids"].get("posts", []):
        charging_ports = []

        if len(nrel_station["ev_connector_types"]) == 1 or station.network not in [ChargingNetwork.EVGO]:
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
        name=station.name.get(),
        charging_port_groups=charging_port_groups,
    )
    charging_point_location = Location(latitude=nrel_station["latitude"], longitude=nrel_station["longitude"])
    charging_point.location.set(SourcedValue(SourceData(SourceLocation.ALTERNATIVE_FUELS_DATA_CENTER, nrel_station["id"]), charging_point_location))

    charging_point.network_id.extend(station.network_id)
    charging_point.nrel_id.extend(station.nrel_id)

    charging_points.append(charging_point)

    return charging_points


def osm_parse_charging_station(osm_element) -> Station:
    station = Station()
    station.osm_id.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), osm_element["id"]))

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

    if "addr:housenumber" in tags and "addr:street" in tags:
        station_street_address = f'{tags["addr:housenumber"]} {tags["addr:street"]}'
        station.street_address.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), station_street_address))

    if "addr:city" in tags:
        station.city.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), tags["addr:city"]))

    if "addr:state" in tags:
        station.state.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), tags["addr:state"]))

    if "addr:postcode" in tags:
        station.zip_code.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), tags["addr:postcode"]))

    if "ref:ocm" in tags:
        for ocm_id in tags["ref:ocm"].split(";"):
            station.ocm_id.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), int(ocm_id)))

    if "ref:afdc" in tags:
        for nrel_id in tags["ref:afdc"].split(";"):
            station.nrel_id.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), int(nrel_id)))

    if "ref:ocpi" in tags:
        for network_id in tags["ref:ocpi"].split(";"):
            station.network_id.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), network_id))

    station.network = network_from_osm_tags(tags)

    return station


def network_from_osm_tags(osm_tags) -> ChargingNetwork:
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

    if "no:network" in osm_tags:
        return ChargingNetwork.NON_NETWORKED

    if "network:wikidata" in osm_tags:
        if network := OSM_NETWORK_WIKIDATA_MAP[osm_tags["network:wikidata"]]:
            return network

    if "network" in osm_tags:
        if network := OSM_NETWORK_NAME_MAP[osm_tags["network"]]:
            return network

    if "operator:wikidata" in osm_tags:
        if network := OSM_OPERATOR_WIKIDATA_NETWORK_MAP[osm_tags["operator:wikidata"]]:
            return network

    if "operator" in osm_tags:
        if network := OSM_OPERATOR_NAME_MAP[osm_tags["operator"]]:
            return network

    if "brand:wikidata" in osm_tags:
        if network := OSM_BRAND_WIKIDATA_NETWORK_MAP[osm_tags["brand:wikidata"]]:
            return network

    if "brand" in osm_tags:
        if network := OSM_BRAND_NAME_NETWORK_MAP[osm_tags["brand"]]:
            return network

    if "name" in osm_tags:
        station_name = osm_tags["name"].lower()

        if "supercharger" in station_name or "super charger" in station_name:
            return ChargingNetwork.TESLA_SUPERCHARGER

        if "tesla" in station_name and "destination" in station_name:
            return ChargingNetwork.TESLA_DESTINATION

    return None


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

    charging_point = ChargingPoint()

    charging_point_location = Location(latitude=osm_element["lat"], longitude=osm_element["lon"])
    charging_point.location.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), charging_point_location))

    charging_point.osm_id.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), osm_element["id"]))

    if "name" in osm_tags:
        charging_point.name = osm_tags["name"]
    elif "ref" in osm_tags:
        charging_point.name = osm_tags["ref"]

    socket_counts: dict[PlugType, int] = {}

    for tag_name, tag_value in osm_tags.items():
        if not tag_name.startswith("socket:"):
            continue

        if tag_name.count(":") > 1:
            continue

        _, socket_type = tag_name.split(":")

        socket_counts[OSM_SOCKETS_TO_PLUGS[socket_type]] = int(tag_value)

    charging_point_capacity = int(osm_tags.get("capacity", 1))
    charging_port_groups = guess_charging_port_groups(charging_point_capacity, socket_counts)

    charging_point.charging_port_groups = charging_port_groups

    charging_point._osm_network = network_from_osm_tags(osm_tags)

    if "ref:ocpi" in osm_tags:
        for network_id in osm_tags["ref:ocpi"].split(";"):
            charging_point.network_id.set(SourcedValue(SourceData(SourceLocation.OPEN_STREET_MAP, osm_element["id"]), network_id))

    return charging_point


def guess_charging_port_groups(capacity: int, plug_counts: dict[PlugType, int]) -> list[ChargingPortGroup]:
    charging_port_groups = []

    if sum(plug_counts.values()) == capacity:
        for socket_type, socket_count in plug_counts.items():
            for _ in range(socket_count):
                charging_port_group = ChargingPortGroup(
                    charging_ports=[ChargingPort(plug=socket_type)]
                )
                charging_port_groups.append(charging_port_group)
    elif capacity == 1 and plug_counts:
        charging_port_group = ChargingPortGroup()

        for socket_type in plug_counts.keys():
            charging_port = ChargingPort(plug=socket_type)
            charging_port_group.charging_ports.append(charging_port)

        charging_port_groups.append(charging_port_group)
    elif capacity and plug_counts:
        print("Uneven plugs to capacity detected:", capacity, plug_counts)

    return charging_port_groups


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
        charge_point_network = charge_point._osm_network

        for station_id, station in stations.items():
            if charge_point_network != station.network:
                continue

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


def normalize_supercharge_data(supercharge_raw_data) -> list[Station]:
    SC_PLUG_TYPE_TO_PLUG_MAP = {
        "ccs1": PlugType.J1772_COMBO,
        "nacs": PlugType.NACS,
        "tpc": PlugType.NACS,

        "multi": None,
    }

    stations = []

    for sc_station in supercharge_raw_data:
        if sc_station["status"] not in ["OPEN", "EXPANDING"]:
            continue

        station_address = sc_station["address"]

        if station_address["countryId"] != 100:
            continue

        if station_address["state"] != "MA":
            continue

        station = Station(
            network=ChargingNetwork.TESLA_SUPERCHARGER,
        )

        station.name.set(SourcedValue(SourceData(SourceLocation.SUPERCHARGE, sc_station["id"]), sc_station["name"]))

        station_location = Location(latitude=sc_station["gps"]["latitude"], longitude=sc_station["gps"]["longitude"])
        station.location.set(SourcedValue(SourceData(SourceLocation.SUPERCHARGE, sc_station["id"]), station_location))

        station.network_id.set(SourcedValue(SourceData(SourceLocation.SUPERCHARGE, sc_station["id"]), sc_station["locationId"]))

        if "osmId" in sc_station:
            station.osm_id.set(SourcedValue(SourceData(SourceLocation.SUPERCHARGE, sc_station["id"]), sc_station["osmId"]))

        station.street_address.set(SourcedValue(SourceData(SourceLocation.SUPERCHARGE, sc_station["id"]), normalize_address_street_address(station_address["street"])))
        station.city.set(SourcedValue(SourceData(SourceLocation.SUPERCHARGE, sc_station["id"]), station_address["city"]))
        station.state.set(SourcedValue(SourceData(SourceLocation.SUPERCHARGE, sc_station["id"]), station_address["state"]))
        station.zip_code.set(SourcedValue(SourceData(SourceLocation.SUPERCHARGE, sc_station["id"]), station_address["zip"]))

        capacity = sc_station["stallCount"]
        plug_counts: dict[PlugType, int] = {}

        for plug_key, count in sc_station["plugs"].items():
            plug_type = SC_PLUG_TYPE_TO_PLUG_MAP[plug_key]

            if not plug_type:
                continue

            if not count:
                count = capacity

            plug_counts[plug_type] = count

        station.charging_points = guess_charging_point_groups(capacity, plug_counts)

        for charging_point in station.charging_points:
            charging_point.location.extend(station.location)

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


def combine_networked_stations_at_same_address(all_stations: list[Station]) -> list[Station]:
    def check_same_address(first_station: Station, second_station: Station) -> bool:
        if not station_networks_match(first_station, second_station):
            return False

        first_addresses = set(map(str.lower, first_station.street_address.all()))
        second_addresses = set(map(str.lower, second_station.street_address.all()))

        if not first_addresses or not second_addresses:
            return False

        if not (first_addresses & second_addresses):
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.1:
            return False

        return True

    return combine_stations_with_check(all_stations, check_same_address)

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

    return combine_stations_with_check(all_stations, check_same_address)

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

    return combine_stations_with_check(all_stations, check_close_location)

def combine_non_networked_stations_at_same_address(all_stations: list[Station]) -> list[Station]:
    def check_same_address(first_station: Station, second_station: Station) -> bool:
        if first_station.network is not ChargingNetwork.NON_NETWORKED:
            return False

        if second_station.network is not ChargingNetwork.NON_NETWORKED:
            return False

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

    return combine_stations_with_check(all_stations, check_same_address)

def combine_non_networked_stations_close_by(all_stations: list[Station]) -> list[Station]:
    def check_non_networked_close_by(first_station: Station, second_station: Station) -> bool:
        if first_station.network is not ChargingNetwork.NON_NETWORKED:
            return False

        if second_station.network is not ChargingNetwork.NON_NETWORKED:
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.01:
            return False

        return True

    return combine_stations_with_check(all_stations, check_non_networked_close_by)

def combine_networked_stations_with_unknown_ones_near_by(all_stations: list[Station]) -> list[Station]:
    def check_unknown_networked_close_by(first_station: Station, second_station: Station) -> bool:
        if first_station.network is not None and second_station.network is not None:
            return False

        if first_station.network is ChargingNetwork.NON_NETWORKED or second_station.network is ChargingNetwork.NON_NETWORKED:
            return False

        if first_station.network is None and second_station.network is None:
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.01:
            return False

        return True

    return combine_stations_with_check(all_stations, check_unknown_networked_close_by)

def combine_non_networked_stations_with_unknown_ones_near_by(all_stations: list[Station]) -> list[Station]:
    def check_unknown_networked_close_by(first_station: Station, second_station: Station) -> bool:
        if first_station.network is not None and second_station.network is not None:
            return False

        if first_station.network is not ChargingNetwork.NON_NETWORKED and second_station.network is not ChargingNetwork.NON_NETWORKED:
            return False

        station_distance = get_station_distance(first_station, second_station)

        if station_distance.miles > 0.01:
            return False

        return True

    return combine_stations_with_check(all_stations, check_unknown_networked_close_by)


def station_networks_match(first_station: Station, second_station: Station) -> bool:
    if first_station.network is None or first_station.network is ChargingNetwork.NON_NETWORKED:
        return False

    if second_station.network is None or second_station.network is ChargingNetwork.NON_NETWORKED:
        return False

    return first_station.network == second_station.network

def combine_stations_with_check(all_stations: list[Station], check) -> list[Station]:
    combined_stations = []

    for first_station in all_stations:
        if getattr(first_station, "matched_network", False):
            continue

        for second_station in all_stations:
            if getattr(second_station, "matched_network", False):
                continue

            if first_station == second_station:
                continue

            if not check(first_station, second_station):
                continue

            combined_station = merge_stations(first_station, second_station)

            first_station.matched_network = True
            second_station.matched_network = True

            first_station = combined_station

        combined_stations.append(first_station)

    return combined_stations


def station_ids_match(first_station: Station, second_station: Station) -> bool:
    if (first_osm := first_station.osm_id.get()) and (second_osm := second_station.osm_id.get()):
        if set(first_osm) & set(second_osm):
            return True

    if (first_ocm := first_station.ocm_id.get()) and (second_ocm := second_station.ocm_id.get()):
        if set(first_ocm) & set(second_ocm):
            return True

    if (first_nrel := first_station.nrel_id.get()) and (second_nrel := second_station.nrel_id.get()):
        if set(first_nrel) & set(second_nrel):
            return True

    return False


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

            if station_ids_match(station, other_station):
                combined_station = merge_stations(station, other_station)

                station.matched_ids = True
                other_station.matched_ids = True

                station = combined_station

        combined_stations.append(station)

    return combined_stations


def combine_stations(all_stations: list[Station]) -> list[Station]:
    all_stations = combine_matched_stations_by_ids(all_stations)
    all_stations = combine_tesla_superchargers(all_stations)

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

    for sourced_value in sorted(sourced_attribute.values, key=lambda v: (-SourceLocationQualityScore[v.source.location.name].value, v.value, v.source.url)):
        source = sourced_value.source

        property_value = {
            "value": sourced_value.value,
            "source": {
                "name": source.location.name,
                "url": source.url,
            }
        }

        property_values.append(property_value)

    return property_values


def addresses_from_station(station: Station) -> list:
    addresses = []

    sourced_information: dict[SourceData, ] = defaultdict(dict)

    for street_address in station.street_address.values:
        sourced_information[street_address.source]["street_address"] = street_address.value

    for city in station.city.values:
        sourced_information[city.source]["city"] = city.value

    for state in station.state.values:
        sourced_information[state.source]["state"] = state.value

    for zip_code in station.zip_code.values:
        sourced_information[zip_code.source]["zip_code"] = zip_code.value

    for source, address in sourced_information.items():
        addresses.append({
            "address": address,
            "source": {
                "name": source.location.name,
                "url": source.url,
            }
        })

    return sorted(addresses, key=lambda a: (-SourceLocationQualityScore[a["source"]["name"]].value, -len(a["address"]), a["source"]["url"]))


with open("nrel-clean.json", "r") as nrel_fh:
    nrel_raw_data = json.load(nrel_fh)

with open("osm-clean.json", "r") as osm_fh:
    osm_raw_data = json.load(osm_fh)

with open("ocm-clean.json", "r") as ocm_fh:
    ocm_raw_data = json.load(ocm_fh)

with open("supercharge-clean.json", "r") as supercharge_fh:
    supercharge_raw_data = json.load(supercharge_fh)

nrel_data = normalize_nrel_data(nrel_raw_data)
osm_data = normalize_osm_data(osm_raw_data)
ocm_data = normalize_ocm_data(ocm_raw_data)
supercharge_data = normalize_supercharge_data(supercharge_raw_data)

combined_data = combine_stations([*nrel_data, *osm_data, *ocm_data, *supercharge_data])

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
        station_properties["name"] = sourced_attribute_to_geojson_property(station.name)
    if station.network:
        station_properties["network"] = station.network.name
    if station.network_id.get():
        station_properties["network_id"] = sourced_attribute_to_geojson_property(station.network_id)

    if station_addresses := addresses_from_station(station):
        station_properties["address"] = station_addresses

    station_references = list()

    station_references.extend(sourced_attribute_to_geojson_property(station.nrel_id))
    station_references.extend(sourced_attribute_to_geojson_property(station.ocm_id))
    station_references.extend(sourced_attribute_to_geojson_property(station.osm_id))

    station_references_unique = set()

    station_references = [reference for reference in station_references if reference["source"]["url"] not in station_references_unique and not station_references_unique.add(reference["source"]["url"])]

    if station_references:
        station_properties["references"] = [ref["source"] for ref in sorted(station_references, key=lambda r: r["source"]["url"])]

    if station.charging_points:
        charging_points = []

        for station_charging_point in sorted(station.charging_points, key=lambda c: (c.name, c.network_id.get())):
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

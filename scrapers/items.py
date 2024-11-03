import scrapy


class ReferenceFeature(scrapy.Item):
    identifier: str = scrapy.Field()
    system: str = scrapy.Field()


class SourceFeature(scrapy.Item):
    quality: str = scrapy.Field()
    system: str = scrapy.Field()


class AddressFeature(scrapy.Item):
    street_address: str = scrapy.Field()
    city: str = scrapy.Field()
    state: str = scrapy.Field()
    zip_code: str = scrapy.Field()


class LocationFeature(scrapy.Item):
    latitude: float = scrapy.Field()
    longitude: float = scrapy.Field()


class HardwareFeature(scrapy.Item):
    manufacturer: str = scrapy.Field()
    model: str = scrapy.Field()
    brand: str = scrapy.Field()


class PowerFeature(scrapy.Item):
    amperage: int = scrapy.Field()
    voltage: int = scrapy.Field()
    output: int = scrapy.Field()


class ChargingPortFeature(scrapy.Item):
    plug: str = scrapy.Field()

    power: PowerFeature = scrapy.Field()

class EvseFeature(scrapy.Item):
    plugs: list[ChargingPortFeature] = scrapy.Field()

    network_id: str = scrapy.Field()


class ChargingPointFeature(scrapy.Item):
    name: str = scrapy.Field()
    location: LocationFeature = scrapy.Field()

    network_id: str = scrapy.Field()

    evses: list[EvseFeature] = scrapy.Field()

    hardware: HardwareFeature = scrapy.Field()


class StationFeature(scrapy.Item):
    name: str = scrapy.Field()

    location: LocationFeature = scrapy.Field()
    address: AddressFeature = scrapy.Field()

    network: str = scrapy.Field()
    network_id: str = scrapy.Field()

    charging_points: list[ChargingPointFeature] = scrapy.Field()

    references: list[ReferenceFeature] = scrapy.Field()
    source: SourceFeature = scrapy.Field()

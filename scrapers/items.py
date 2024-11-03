import scrapy


class ReferenceFeature(scrapy.Item):
    identifier = scrapy.Field()
    system = scrapy.Field()


class SourceFeature(scrapy.Item):
    quality = scrapy.Field()
    system = scrapy.Field()


class AddressFeature(scrapy.Item):
    street_address = scrapy.Field()
    city = scrapy.Field()
    state = scrapy.Field()
    zip_code = scrapy.Field()


class LocationFeature(scrapy.Item):
    latitude = scrapy.Field()
    longitude = scrapy.Field()


class HardwareFeature(scrapy.Item):
    manufacturer = scrapy.Field()
    model = scrapy.Field()
    brand = scrapy.Field()


class PowerFeature(scrapy.Item):
    amperage = scrapy.Field()
    voltage = scrapy.Field()
    output = scrapy.Field()


class ChargingPortFeature(scrapy.Item):
    plug = scrapy.Field()

    power = scrapy.Field()

class EvseFeature(scrapy.Item):
    plugs = scrapy.Field()

    network_id = scrapy.Field()


class ChargingPointFeature(scrapy.Item):
    name = scrapy.Field()
    location = scrapy.Field()

    network_id = scrapy.Field()

    evses = scrapy.Field()

    hardware = scrapy.Field()


class StationFeature(scrapy.Item):
    name = scrapy.Field()

    location = scrapy.Field()
    address = scrapy.Field()

    network = scrapy.Field()
    network_id = scrapy.Field()

    charging_points = scrapy.Field()

    references = scrapy.Field()
    source = scrapy.Field()

from scrapers.spiders.evgateway import EvGatewaySpider


class EnergyFiveSpider(EvGatewaySpider):
    name = "zeplug"
    org_id = 392
    network_name = "ZEPLUG"

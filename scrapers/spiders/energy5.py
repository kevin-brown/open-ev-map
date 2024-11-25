from scrapers.spiders.evgateway import EvGatewaySpider


class EnergyFiveSpider(EvGatewaySpider):
    name = "energy5"
    org_id = 885
    network_name = "ENERGY5"

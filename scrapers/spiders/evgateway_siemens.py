from scrapers.spiders.evgateway import EvGatewaySpider


class SiemensSpider(EvGatewaySpider):
    name = "evgateway_siemens"
    org_id = 531
    network_name = "EV_GATEWAY"

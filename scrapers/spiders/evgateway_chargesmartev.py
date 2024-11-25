from scrapers.spiders.evgateway import EvGatewaySpider


class ChargeSmartEvSpider(EvGatewaySpider):
    name = "evgateway_chargesmartev"
    org_id = 632
    network_name = "CHARGESMART_EV"

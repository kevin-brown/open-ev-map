from scrapers.spiders.evconnect import EvConnectSpider


class GreenSpotSpider(EvConnectSpider):
    name = "greenspot"
    ev_connect_network = "greenspot"
    network_name = "GREEN_SPOT"

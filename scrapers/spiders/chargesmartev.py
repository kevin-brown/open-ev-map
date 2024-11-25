from scrapers.spiders.evconnect import EvConnectSpider


class ChargeSmartEvSpider(EvConnectSpider):
    name = "chargesmartev"
    ev_connect_network = "chargesmartev"
    network_name = "CHARGESMART_EV"

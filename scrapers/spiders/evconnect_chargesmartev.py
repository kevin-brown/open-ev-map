from scrapers.spiders.evconnect import EvConnectSpider


class ChargeSmartEvSpider(EvConnectSpider):
    name = "evconnect_chargesmartev"
    ev_connect_network = "chargesmartev"
    network_name = "CHARGESMART_EV"
    ocpi_cpo_id = "CSE"

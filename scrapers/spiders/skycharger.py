from scrapers.spiders.evconnect import EvConnectSpider


class SkyChargerSpider(EvConnectSpider):
    name = "skycharger"
    ev_connect_network = "skycharger"
    network_name = "SKYCHARGER"
    ocpi_cpo_id = "SKY"

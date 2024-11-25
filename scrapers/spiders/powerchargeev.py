from scrapers.spiders.evconnect import EvConnectSpider


class PowerChargeEvSpider(EvConnectSpider):
    name = "powerchargeev"
    ev_connect_network = "powerchargeev"
    network_name = "POWER_CHARGE_CONNECT"

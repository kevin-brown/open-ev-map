from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, StationFeature

import scrapy


class OcpiSpider(scrapy.Spider):
    STANDARD_TO_PLUG_TYPE_MAP = {
        "IEC_62196_T1": "J1772_CABLE",
        "IEC_62196_T1_COMBO": "J1772_COMBO",
        "CHADEMO": "CHADEMO",
    }

    def station_to_feature(self, station):
        location = LocationFeature(**station["coordinates"])
        address = AddressFeature(
            street_address=station["address"],
            city=station["city"],
            state=station["state"],
            zip_code=station["postal_code"],
        )

        charging_points = []

        for station_evse in station["evses"]:
            plugs = []

            for connector in station_evse["connectors"]:
                if "max_electric_power" in connector:
                    output = int(connector["max_electric_power"])
                else:
                    output = connector["max_amperage"] * connector["max_voltage"]

                power = PowerFeature(
                    amperage=connector["max_amperage"],
                    voltage=connector["max_voltage"],
                    output=output,
                )

                plug = ChargingPortFeature(
                    plug=self.STANDARD_TO_PLUG_TYPE_MAP[connector["standard"]],

                    power=power,
                )
                plugs.append(plug)

            evse = EvseFeature(
                plugs=plugs,
            )

            hardware = HardwareFeature()

            if "manufacturer" in station_evse:
                hardware["manufacturer"] = station_evse["manufacturer"]

            if "model" in station_evse:
                hardware["model"] = station_evse["model"]

            if "brand" in station_evse:
                hardware["brand"] = station_evse["brand"]

            charging_point = ChargingPointFeature(
                name=station_evse["physical_reference"],
                network_id=station_evse["evse_id"],
                location=location,
                evses=[evse],
                hardware=hardware,
            )
            charging_points.append(charging_point)

        yield StationFeature(
            name=station["name"],
            network=self.network,
            network_id=station["id"],
            location=location,
            address=address,
            charging_points=charging_points,
        )

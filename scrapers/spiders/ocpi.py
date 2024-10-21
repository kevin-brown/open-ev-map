from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, LocationFeature, StationFeature

import scrapy


class OcpiSpider(scrapy.Spider):
    STANDARD_TO_PLUG_TYPE_MAP = {
        "IEC_62196_T1": "J1772",
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

                plug = ChargingPortFeature(
                    plug=self.STANDARD_TO_PLUG_TYPE_MAP[connector["standard"]],

                    amperage=connector["max_amperage"],
                    voltage=connector["max_voltage"],
                    output=output,
                )
                plugs.append(plug)

            evse = EvseFeature(
                plugs=plugs,
            )

            charging_point = ChargingPointFeature(
                name=station_evse["physical_reference"],
                network_id=station_evse["evse_id"],
                location=location,
                evses=[evse],
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

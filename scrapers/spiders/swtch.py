from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

from scrapy.utils.project import get_project_settings
import scrapy

from urllib.parse import urlencode


class SwtchSpider(scrapy.Spider):
    name = "swtch"

    CONNECTOR_TYPE_TO_PLUG = {
        "CCS": "J1772_COMBO",
        "J1772": "J1772_CABLE",

        "IEC_62196_T1": "J1772_CABLE",
    }

    def _query_for_bounding_box(self, lat, lng, radius, zoom):
        return {
            "lat": lat,
            "lng": lng,
            "radius": radius,
            "zoom": zoom,
        }

    def start_requests(self):
        query = self._query_for_bounding_box(
            lat=42.13,
            lng=-71.76,
            radius=145,
            zoom=7,
        )

        yield scrapy.http.JsonRequest(
            url="https://charge.swtchenergy.com/api/v2/public/nearest_charger?" + urlencode(query),
            meta={
                "query": query,
            },
            callback=self.parse_nearest_chargers,
        )
    
    def parse_nearest_chargers(self, response):
        data = response.json()

        clusters = data["data"]
        stations = []

        for cluster in clusters:
            if "id" in cluster:
                stations.append(cluster)

                continue

            query = self._query_for_bounding_box(
                lat=cluster["latitude"],
                lon=cluster["longitude"],
                radius=cluster["size"],
                zoom=response.meta["query"]["zoom"] + 1,
            )

            yield scrapy.http.JsonRequest(
                url="https://charge.swtchenergy.com/api/v2/public/nearest_charger?" + urlencode(query),
                meta={
                    "query": query,
                },
                callback=self.parse_nearest_chargers,
            )

        if "clusters" in data:
            for cluster in data["clusters"]:
                stations.extend(cluster)

        settings = get_project_settings()

        for station in stations:
            yield scrapy.http.JsonRequest(
                url=f"https://charge.swtchenergy.com/api/v2/user/listings/{station["id"]}",
                headers={
                    "Authorization": f"Bearer {settings.get("SWTCH_ACCESS_TOKEN")}",
                },
                meta={
                    "station": station,
                },
                callback=self.parse_listing,
            )

    def parse_listing(self, response):
        data = response.json()

        if data["operator"] == "CA-SWT":
            yield from self.parse_swtch_listing(data)
        else:
            cpo = data["operator"][3:6]

            if cpo == "ZEF":
                pass
            else:
                print(cpo, data)
                raise
    
    def parse_swtch_listing(self, data):
        location = data["location"]
        tenant = data["tenant"]
        charger = data["connector"]["charger"]
        listing = data["connector"]["listing"]

        if location["province"] != "MA":
            return

        street_address = location["address"]

        if " " not in street_address:
            street_address = street_address.replace("-", " ")

        address = AddressFeature(
            street_address=street_address,
            city=location["city"],
            state=location["province"],
            zip_code=location["postalCode"],
        )

        coordinates = LocationFeature(
            latitude=location["latitude"],
            longitude=location["longitude"],
        )

        evses = []

        for connector in data["connectors"]:
            plug = ChargingPortFeature(
                plug=self.CONNECTOR_TYPE_TO_PLUG[connector["connector_type"]],
                power=PowerFeature(
                    output=data["charger"]["maxWatt"],
                )
            )

            evse = EvseFeature(
                network_id=f"CA*SWT*E{connector["id"]}",
                plugs=[
                    plug,
                ],
            )

            evses.append(evse)

        charging_point = ChargingPointFeature(
            name=listing["title"],
            network_id=charger["id"],
            hardware=HardwareFeature(
                model=charger["charge_point_model"],
                manufacturer=charger["charge_point_vendor"],
            ),
            evses=evses,
        )

        yield StationFeature(
            name=tenant["name"],
            network="SWTCH",
            network_id=tenant["id"],
            location=coordinates,
            address=address,
            charging_points=[
                charging_point,
            ],
            source=SourceFeature(
                system="SWTCH_V2",
                quality="ORIGINAL",
            )
        )

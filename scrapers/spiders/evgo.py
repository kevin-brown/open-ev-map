from scrapers.items import AddressFeature, ChargingPointFeature, ChargingPortFeature, EvseFeature, HardwareFeature, LocationFeature, PowerFeature, SourceFeature, StationFeature

from uszipcode.state_abbr import MAPPER_STATE_ABBR_LONG_TO_SHORT
import scrapy


class EvgoSpider(scrapy.Spider):
    name = "evgo"

    CONNECTOR_TO_PLUG_MAP = {
        "CCS Combo": "J1772_COMBO",
        "CCS Combo A": "J1772_COMBO",
        "CCS Combo B": None,
        "CHAdeMO": "CHADEMO",
        "Tesla": "NACS",
        "L2": "J1772_CABLE",
    }

    def _query_for_bounding_box(self, sw_lon, sw_lat, ne_lon, ne_lat):
        return {
            "filterByIsManaged": True,
            "filterByBounds": {
                "southWestLng": sw_lon,
                "southWestLat": sw_lat,
                "northEastLng": ne_lon,
                "northEastLat": ne_lat,
            },
        }

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://firebaseinstallations.googleapis.com/v1/projects/evgo-falcon-prod/installations",
            headers={
                "x-firebase-client": "H4sIAAAAAAAAAKtWykhNLCpJSk0sKVayio7VUSpLLSrOzM9TslIyUqoFAFyivEQfAAAA",
                "x-goog-api-key": "AIzaSyB3lt9BT-8YCybXkXuMmL9MXV9zc3823tc",
            },
            data={
                "fid": "fgwtE7l4T-6DdlDNEg2s3R",
                "appId": "1:545807131737:android:9d140d318c3cc4275e7d48",
                "authVersion": "FIS_v2",
                "sdkVersion": "a:17.2.0"
            },
            callback=self.parse_firebase_install,
        )

    def parse_firebase_install(self, response):
        yield scrapy.http.JsonRequest(
            url="https://www.googleapis.com/identitytoolkit/v3/relyingparty/signupNewUser?key=AIzaSyB3lt9BT-8YCybXkXuMmL9MXV9zc3823tc",
            headers={
                "X-Firebase-Client": "H4sIAAAAAAAAAKtWykhNLCpJSk0sKVayio7VUSpLLSrOzM9TslIyUqoFAFyivEQfAAAA",
                "X-Firebase-GMPID":  "1:545807131737:android:9d140d318c3cc4275e7d48",
            },
            data={
                "clientType": "CLIENT_TYPE_ANDROID",
            },
            callback=self.parse_firebase_signup,
        )

    def parse_firebase_signup(self, response):
        response_data = response.json()

        yield scrapy.http.JsonRequest(
            url="https://api.prod.evgo.com/",
            headers={
                "Authorization": "Bearer " + response_data["idToken"],
            },
            data={
                "operationName": "GetEvgoSitesForMobile",
                "variables": {
                    "input": {
                    "distance": 145,
                    "latitude": 42.13,
                    "longitude": -71.76,
                    "outputKwMin": 0,
                    "outputKwMax": 1000,
                    "vehicleConnectorIds": [
                        3,
                        2,
                        1,
                        4
                    ],
                    "plugAndCharge": False
                    }
                },
                "query": """
                    query GetEvgoSitesForMobile($input: EvgoSitesForMobileInput!) {
                        getEvgoSitesForMobile(input: $input) {
                            edges {
                                ...SiteSummaryFragment
                            }
                        }
                    }
                    fragment SiteSummaryFragment on SitesForMobile {
                        altId
                        latitude
                        longitude
                        networkName
                        siteStatus
                    }
                    """,
            },
            meta={
                "id_token": response_data["idToken"],
            },
            method="POST",
            callback=self.parse_site_ids,
        )

    def parse_site_ids(self, response):
        response_data = response.json()

        for site in response_data["data"]["getEvgoSitesForMobile"]["edges"]:
            yield scrapy.http.JsonRequest(
                url="https://api.prod.evgo.com/",
                headers={
                    "apollographql-client-name": "EVgo Android Client",
                    "apollographql-client-version": "9.15.0-21938",
                    "Authorization": "Bearer " + response.meta["id_token"],
                },
                data={
                    "operationName": "GetSingleSite",
                    "variables": site,
                    "query": """
                    query GetSingleSite($altId: ID!, $latitude: Float!, $longitude: Float!) {
                        siteForMobile(input: {altId: $altId, latitude: $latitude, longitude: $longitude}) {
                            altId
                            displayName
                            address1
                            locality
                            administrativeArea
                            postalCode
                            latitude
                            longitude
                            chargers {
                                altId
                                chargerName
                                simultaneousChargingEnabled
                                evses {
                                    altId
                                    connectors {
                                        altId
                                        connectorType
                                        maxPower
                                    }
                                }
                            }
                        }
                    }
                    """
                },
                meta={
                    "id_token": response.meta["id_token"],
                },
            )

    def parse(self, response):
        response_data = response.json()
        station = response_data["data"]["siteForMobile"]

        coordinates = LocationFeature(
            longitude=station["longitude"],
            latitude=station["latitude"],
        )

        address = AddressFeature(
            street_address=station["address1"],
            city=station["locality"],
            state=MAPPER_STATE_ABBR_LONG_TO_SHORT[station["administrativeArea"]],
            zip_code=station["postalCode"],
        )

        charging_points = []

        for charger in station["chargers"]:
            evses = []

            for evse in charger["evses"]:
                charging_ports = []

                for connector in evse["connectors"]:
                    charging_ports.append(ChargingPortFeature(
                        plug=self.CONNECTOR_TO_PLUG_MAP[connector["connectorType"]],
                        power=PowerFeature(
                            output=int(connector["maxPower"] * 1000),
                        ),
                    ))

                evses.append(EvseFeature(
                    network_id=evse["altId"],
                    plugs=charging_ports,
                ))

            charging_points.append(ChargingPointFeature(
                name=charger["chargerName"],
                network_id=charger["altId"],
                evses=evses,
            ))

        yield StationFeature(
            name=station["displayName"],
            network="EVGO",
            network_id=station["altId"],
            location=coordinates,
            address=address,
            charging_points=charging_points,
            source=SourceFeature(
                quality="ORIGINAL",
                system="EVGO",
            ),
        )

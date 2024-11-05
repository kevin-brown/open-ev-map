import scrapy

from scrapers.items import AddressFeature, LocationFeature, SourceFeature, StationFeature


class RivianSpider(scrapy.Spider):
    name = "rivian"

    NETWORK_MAP = {
        "CHARGING-RAN": "RIVIAN_ADVENTURE",
        "CHARGING-RWN": "RIVIAN_WAYPOINTS",
    }

    def start_requests(self):
        yield scrapy.http.JsonRequest(
            url="https://rivian.com/api/gql/content/graphql",
            data=[
                {
                    "operationName": "EgMapBlockLocations",
                    "query": """
                    query EgMapBlockLocations($id: String!, $locale: String, $preview: Boolean) {
                        egMapBlock(id: $id, locale: $locale, preview: $preview) {
                            locationsCollection(limit: 3) {
                                items {
                                    ... on EgLocation {
                                        ...EgLocation
                                        __typename
                                    }
                                    ... on EgLocationCategory {
                                        name
                                        locationsCollection(limit: 300) {
                                            items {
                                                ...EgLocation
                                                __typename
                                            }
                                            __typename
                                        }
                                        __typename
                                    }
                                    __typename
                                }
                                __typename
                            }
                            __typename
                        }
                    }

                    fragment EgLocation on EgLocation {
                        sys {
                            id
                            __typename
                        }
                        address
                        addressHyperlink
                        city
                        country
                        icon {
                            url
                            __typename
                        }
                        selectedIcon {
                            url
                            __typename
                        }
                        lat
                        lon
                        locationType
                        name
                        numberOfChargers
                        postalCode
                        stateOrProvince
                        status
                        phone
                        email
                        hours {
                            strings: stringsCollection(limit: 7) {
                                items {
                                    key
                                    value
                                    __typename
                                }
                                __typename
                            }
                            __typename
                        }
                        __typename
                    }
                    """,
                    "variables": {
                        "id": "3QCSziDH9lXcsI7tFkI3qy",
                    },
                }
            ],
            method="POST",
        )

    def parse(self, response):
        locations_collections = response.json()[0]["data"]["egMapBlock"]["locationsCollection"]["items"]
        rivian_locations = locations_collections[0]
        rivian_chargers = rivian_locations["locationsCollection"]["items"]

        for charger in rivian_chargers:
            coordinates = LocationFeature(
                latitude=charger["lat"],
                longitude=charger["lon"],
            )

            address = AddressFeature(
                street_address=charger["address"],
                city=charger["city"],
                state=charger["stateOrProvince"],
                zip_code=charger["postalCode"]
            )

            network = self.NETWORK_MAP[charger["locationType"]]

            yield StationFeature(
                name=charger["name"],
                network=network,
                location=coordinates,
                address=address,
                source=SourceFeature(
                    quality="ORIGINAL",
                    system="RIVIAN_EG_MAP",
                ),
            )

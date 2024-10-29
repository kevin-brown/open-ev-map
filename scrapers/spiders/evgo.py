import scrapy


class EvgoSpider(scrapy.Spider):
    name = "evgo"

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
        bounds = {
            "ne_lat": 43.0,
            "ne_lon": -69.6,
            "sw_lat": 41.0,
            "sw_lon": -73.6,
        }

        yield scrapy.http.JsonRequest(
            url="https://account.evgo.com/stationFacade/findSitesInBounds",
            headers={
                "x-json-types": "None",
            },
            data=self._query_for_bounding_box(**bounds),
            meta={"bounds": bounds},
            method="GET",
        )

    def parse(self, response):
        response_data = response.json()

        print(response_data)

<script lang="ts">
  import { base } from "$app/paths";

  import { DefaultMarker, MapLibre, Popup } from "svelte-maplibre";

  async function fetchStations() {
    const response = await fetch(base + '/stations.geojson');

    if (response.ok) {
      return response.json().then((featureCollection) => featureCollection.features);
    } else {
      throw new Error();
    }
  }

  function latLngForStation(station) {
    if (station.geometry.type === "Point") {
      return station.geometry.coordinates;
    } else if (station.geometry.type == "MultiPoint") {
      return station.geometry.coordinates[0];
    }
  }

  let stationRequest = fetchStations();
</script>

<h1>Welcome to Open EV Map</h1>

<MapLibre style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" center={[-71.75, 42.25]} zoom={8}>
  {#await stationRequest}
  Loading
  {:then stationMarkers}
    {#each stationMarkers as stationMarker}
      <DefaultMarker lngLat={latLngForStation(stationMarker)}>
        <Popup openOn="click">
            <h3 class="font-bold text-lg">{ stationMarker.properties.name?.split(";")[0] }</h3>
            <p>{ stationMarker.properties.network }</p>
            <p>
              { stationMarker.properties.street_address }, { stationMarker.properties.city },
              { stationMarker.properties.state } { stationMarker.properties.zip_code}
            </p>
        </Popup>
      </DefaultMarker>
    {/each}
  {/await}
</MapLibre>

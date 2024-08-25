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

  function firstPropertyValueForDisplay(propertyValue) {
    if (!propertyValue) {
      return "";
    }

    if (propertyValue.length < 1) {
      return "";
    }

    return propertyValue[0].value;
  }

  function formatStationAddress(stationAddress) {
    if (!stationAddress) {
      return "";
    }

    let address = "";

    if (stationAddress.street_address) {
      address += stationAddress.street_address;
    }

    if (stationAddress.city) {
      if (address) {
        address += ", ";
      }

      address += stationAddress.city;
    }

    if (stationAddress.state) {
      if (address) {
        address += ", ";
      }

      address += stationAddress.state;
    }

    if (stationAddress.zip_code) {
      if (address) {
        address += " ";
      }

      address += stationAddress.zip_code;
    }

    return address;
  }

  function formatPrimaryStationAddress(stationAddresses) {
    if (!stationAddresses) {
      return "";
    }

    if (stationAddresses.length < 1) {
      return "";
    }

    return formatStationAddress(stationAddresses[0].address)
  }

  function formatSourceName(sourceName: string): string {
    const SOURCE_NAME_DISPLAY = {
      "ALTERNATIVE_FUELS_DATA_CENTER": "Alternative Fuels Data Center",
      "OPEN_CHARGE_MAP": "Open Charge Map",
      "OPEN_STREET_MAP": "OpenStreetMap",
      "SUPERCHARGE": "supercharge.info",
    }

    return SOURCE_NAME_DISPLAY[sourceName];
  }
</script>

<h1>Welcome to Open EV Map</h1>

<MapLibre style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" center={[-71.75, 42.25]} zoom={8}>
  {#await stationRequest}
  Loading
  {:then stationMarkers}
    {#each stationMarkers as stationMarker}
      <DefaultMarker lngLat={latLngForStation(stationMarker)}>
        <Popup openOn="click">
            <h3 class="font-bold text-lg">{ firstPropertyValueForDisplay(stationMarker.properties.name) }</h3>
            <p>{ stationMarker.properties.network }</p>
            <p>
              { formatPrimaryStationAddress(stationMarker.properties.address) }
            </p>
            {#if stationMarker.properties.name?.length > 1}
            <h4 class="font-bold">
              Names
            </h4>
            <ul class="list-disc">
              {#each stationMarker.properties.name as name}
              <li>
                {name.value}<br />
                <span class="italic">from <a href={name.source.url} class="underline" target="_blank">{formatSourceName(name.source.name)}</a></span>
              </li>
              {/each}
            </ul>
            {/if}
            {#if stationMarker.properties.address?.length > 1}
            <h4 class="font-bold">
              Addresses
            </h4>
            <ul class="list-disc">
              {#each stationMarker.properties.address as address}
              <li>
                {formatStationAddress(address.address)}<br />
                <span class="italic">from <a href={address.source.url} class="underline" target="_blank">{formatSourceName(address.source.name)}</a></span>
              </li>
              {/each}
            </ul>
            {/if}
            {#if stationMarker.properties.references?.length > 0}
            <h4 class="font-bold">
              Sources
            </h4>
            <ul class="list-disc">
              {#each stationMarker.properties.references as reference}
              <li><a href={reference.url} class="underline" target="_blank">{formatSourceName(reference.name)}</a></li>
              {/each}
              </ul>
            {/if}
        </Popup>
      </DefaultMarker>
    {/each}
  {/await}
</MapLibre>

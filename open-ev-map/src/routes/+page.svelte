<script lang="ts">
  import { base } from "$app/paths";

  import { Marker, MapLibre, Popup } from "svelte-maplibre";

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
      "ELECTRIC_ERA": "Electric Era",
      "ELECTRIFY_AMERICA": "Electrify America",
      "OPEN_CHARGE_MAP": "Open Charge Map",
      "OPEN_STREET_MAP": "OpenStreetMap",
      "SUPERCHARGE": "supercharge.info",
    }

    return SOURCE_NAME_DISPLAY[sourceName];
  }

  function iconPathForPlugType(plugType: string): string {
    const PLUG_TYPE_MAP = {
      'CHADEMO': 'chademo',
      'J1772': 'j1772',
      'J1772_COMBO': 'j1772-combo',
      'NACS': 'nacs',
    }

    return base + '/icons/plug-' + PLUG_TYPE_MAP[plugType] + '.svg';
  }

  function stationMarkerColor(station): string {
    if (!station.properties.references) {
      return "gray";
    }

    if (station.properties.references.length < 1) {
      return "gray";
    }

    let referenceSources = station.properties.references.map((r) => r.name);

    if (referenceSources.includes("OPEN_STREET_MAP")) {
      return "green";
    }

    if (referenceSources.includes("OPEN_CHARGE_MAP")) {
      return "blue";
    }

    if (referenceSources.includes("ALTERNATIVE_FUELS_DATA_CENTER")) {
      return "orange";
    }

    return "yellow";
  }

  function* chunks<T>(arr: T[], n: number): Generator<T[], void> {
    for (let i = 0; i < arr.length; i += n) {
      yield arr.slice(i, i + n);
    }
  }
</script>

<h1>Welcome to Open EV Map</h1>

<MapLibre style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" center={[-71.75, 42.25]} zoom={8} standardControls>
  {#await stationRequest}
  Loading
  {:then stationMarkers}
    {#each stationMarkers as stationMarker}
      <Marker lngLat={latLngForStation(stationMarker)}>
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
          <path
            fill={stationMarkerColor(stationMarker)}
            d="M14 11.5A2.5 2.5 0 0 0 16.5 9A2.5 2.5 0 0 0 14 6.5A2.5 2.5 0 0 0 11.5 9a2.5 2.5 0 0 0 2.5 2.5M14 2c3.86 0 7 3.13 7 7c0 5.25-7 13-7 13S7 14.25 7 9a7 7 0 0 1 7-7M5 9c0 4.5 5.08 10.66 6 11.81L10 22S3 14.25 3 9c0-3.17 2.11-5.85 5-6.71C6.16 3.94 5 6.33 5 9Z"
          />
        </svg>

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
            <ul class="list-disc px-4">
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
            <ul class="list-disc px-4">
              {#each stationMarker.properties.address as address}
              <li>
                {formatStationAddress(address.address)}<br />
                <span class="italic">from <a href={address.source.url} class="underline" target="_blank">{formatSourceName(address.source.name)}</a></span>
              </li>
              {/each}
            </ul>
            {/if}
            {#if stationMarker.properties.charging_points?.length > 0}
            <h4 class="font-bold">
              Charging Points
            </h4>
            <div class="grid-cols-1 grid-cols-2 grid-cols-3"></div>
            <div class="grid grid-cols-{Math.min(stationMarker.properties.charging_points.length, 3)} gap-4">
              {#each stationMarker.properties.charging_points as chargingPoint}
              <div>
                <table class="border">
                  <thead>
                    <tr>
                      <td colspan={Math.min(chargingPoint.charging_groups.length, 4)}>
                        {chargingPoint.name}
                        {#if chargingPoint.network_id?.length > 0}
                        {#if chargingPoint.name}<br />{/if}
                        ({firstPropertyValueForDisplay(chargingPoint.network_id)})
                        {/if}
                      </td>
                    </tr>
                  </thead>
                  <tbody>
                    {#each chunks(chargingPoint.charging_groups, 4) as chargingGroupsChunk}
                    <tr>
                      {#each chargingGroupsChunk as chargingGroup}
                      <td class="border">
                        <table class="border">
                          {#if chargingGroup.network_id}
                          <thead>
                            <tr>
                              <td colspan={Math.min(chargingGroup.ports.length, 4)} class="border-b">
                                {chargingGroup.network_id}
                              </td>
                            </tr>
                          </thead>
                          {/if}
                          <tbody>
                            {#each chunks(chargingGroup.ports, 4) as groupPortsChunk}
                            <tr>
                              {#each groupPortsChunk as chargingPort}
                              <td class="border">
                                <img src={iconPathForPlugType(chargingPort.plug_type)} alt={chargingPort.plug_type} height="50px" width="50px" class="mx-auto" />
                              </td>
                              {/each}
                            </tr>
                            {/each}
                          </tbody>
                        </table>
                      </td>
                      {/each}
                    </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
              {/each}
            </div>
            {/if}
            {#if stationMarker.properties.references?.length > 0}
            <h4 class="font-bold">
              Sources
            </h4>
            <ul class="list-disc px-4">
              {#each stationMarker.properties.references as reference}
              <li>
                <a href={reference.url} class="underline" target="_blank">{formatSourceName(reference.name)}</a>
              </li>
              {/each}
              </ul>
            {/if}
        </Popup>
      </Marker>
    {/each}
  {/await}
</MapLibre>

<script lang="ts">
  import { Marker, MapLibre, Popup } from "svelte-maplibre";

  import { firstPropertyValueForDisplay, formatPrimaryStationAddress } from "$lib/formatters";
  import { fetchStations } from "$lib/stations";

  function latLngForStation(station) {
    if (station.geometry.type === "Point") {
      return station.geometry.coordinates;
    } else if (station.geometry.type == "MultiPoint") {
      return station.geometry.coordinates[0];
    }
  }

  let stationRequest = fetchStations();

  function stationMarkerColor(station): string {
    if (!station.properties.references) {
      return "gray";
    }

    if (station.properties.references.length < 1) {
      return "gray";
    }

    let referenceSources = new Set(station.properties.references.map((r) => r.name));

    if (referenceSources.has("OPEN_STREET_MAP")) {
      return "green";
    }

    if (referenceSources.has("OPEN_CHARGE_MAP")) {
      return "blue";
    }

    if (referenceSources.has("ALTERNATIVE_FUELS_DATA_CENTER")) {
      if (station.properties.network_id?.length > 0) {
        return "orange";
      }

      if (!station.properties.network || station.properties.network == "NON_NETWORKED") {
        return "orange";
      }
    }

    if (referenceSources.has("ALTERNATIVE_FUELS_DATA_CENTER") && referenceSources.size === 1) {
      if (station.properties.network == "AMP_UP" || station.properties.network == "TESLA_DESTINATION") {
        return "";
      }
    }

    return "red";
  }

  function plugsForStation(station): string[] {
    if (!station.properties.charging_points) {
      return [];
    }

    return station.properties.charging_points.flatMap((point) => {
      if (!point.charging_groups) {
        return [];
      }

      return point.charging_groups.flatMap((group) => {
        if (!group.ports) {
          return [];
        }

        return group.ports.map((port) => port.plug_type);
      });
    }).filter((value: string, index: number, array: string[]) => array.indexOf(value) === index);
  }

  function osmUrlForStation(station): string | null {
    if (!station.properties.references) {
      return null;
    }

    for (let reference of station.properties.references) {
      if (reference.name == "OPEN_STREET_MAP") {
        return reference.url;
      }
    }

    return null;
  }
</script>

<h1>Welcome to Open EV Map</h1>

<MapLibre style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json" center={[-71.75, 42.25]} zoom={8} standardControls>
  {#await stationRequest}
  Loading
  {:then stationMarkers}
    {#each stationMarkers as stationMarker}
      <Marker lngLat={latLngForStation(stationMarker)}>
        {#if stationMarkerColor(stationMarker)}
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
          <path
            fill={stationMarkerColor(stationMarker)}
            d="M14 11.5A2.5 2.5 0 0 0 16.5 9A2.5 2.5 0 0 0 14 6.5A2.5 2.5 0 0 0 11.5 9a2.5 2.5 0 0 0 2.5 2.5M14 2c3.86 0 7 3.13 7 7c0 5.25-7 13-7 13S7 14.25 7 9a7 7 0 0 1 7-7M5 9c0 4.5 5.08 10.66 6 11.81L10 22S3 14.25 3 9c0-3.17 2.11-5.85 5-6.71C6.16 3.94 5 6.33 5 9Z"
          />
        </svg>
        {/if}

        <Popup openOn="click">
            <h3 class="font-bold text-lg">{ firstPropertyValueForDisplay(stationMarker.properties.name) }</h3>
            <p>{ stationMarker.properties.network } - <a href="/networks/{stationMarker.properties.network?.toLowerCase()}/stations/{firstPropertyValueForDisplay(stationMarker.properties.network_id)}">details</a></p>
            <p>
              { formatPrimaryStationAddress(stationMarker.properties.address) }
            </p>
            <p>
              { stationMarker.properties.charging_points?.length || 0 } stations
            </p>
            {@const plugs = plugsForStation(stationMarker) }
            {#if plugs?.length > 0}
            <p>
              Plugs: { plugs.join(", ") }
            </p>
            {/if}
            {@const osmUrl = osmUrlForStation(stationMarker) }
            {#if osmUrl}
            <p>
              <a href={osmUrl}>[OSM]</a>
            </p>
            {/if}
        </Popup>
      </Marker>
    {/each}
  {/await}
</MapLibre>

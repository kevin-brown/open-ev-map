<script lang="ts">
  import { firstPropertyValueForDisplay } from "$lib/formatters";

  function openStreetMapLink(station): string {
    let references = station.properties.references || [];
    let osmReference = references.find((ref) => ref.name == "OPEN_STREET_MAP");

    if (!osmReference) {
      return "";
    }

    return osmReference.url;
  }

  export let data;
</script>

<svelte:head>
  <title>{firstPropertyValueForDisplay(data.station.properties.name)} - Open EV Map</title>
</svelte:head>

<h2>{firstPropertyValueForDisplay(data.station.properties.name)}</h2>
{data.station.properties.network} <a href={openStreetMapLink(data.station)}>Open Street Map</a>

<slot></slot>
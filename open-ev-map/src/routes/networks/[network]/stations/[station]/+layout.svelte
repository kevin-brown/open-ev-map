<script lang="ts">
  function stationName(station): string {
    return station.properties.name && station.properties.name.length > 0 ? station.properties.name[0].value : "";
  }

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

<h2>{stationName(data.station)}</h2>
{data.station.properties.network} <a href={openStreetMapLink(data.station)}>Open Street Map</a>

<slot></slot>
<script lang="ts">
  function stationName(station): string {
    return station.properties.name && station.properties.name.length > 0 ? station.properties.name[0].value : "";
  }

  export let data;
</script>

{data.station.properties.network}
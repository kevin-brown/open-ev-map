<script lang="ts">
	import { page } from '$app/stores';

  function stationName(station): string {
    return station.properties.name && station.properties.name.length > 0 ? station.properties.name[0].value : "";
  }

  export let data;
</script>

<h2>{stationName(data.station)}</h2>
{data.station.properties.network}
<a href="/networks/{$page.params.network}/stations/{$page.params.station}/edit">Edit</a>
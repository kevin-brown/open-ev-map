<script lang="ts">
  import { base } from "$app/paths";

  function stationName(station): string {
    return station.properties.name && station.properties.name.length > 0 ? station.properties.name[0].value : "";
  }

  export let data;

  let editStation = {
    name: '',
    network: '',
    network_id: '',
    charging_points: [{
      name: 'test',
    }],
  };

  let sourcedProperties = ['name', 'network_id'];
  let unsourcedProperties = ['charging_points', 'network'];

  sourcedProperties.forEach((propName) => {
    if (data.station.properties[propName] && data.station.properties[propName].length > 0) {
      let firstChoice = data.station.properties[propName].find((propChoice) => propChoice.source.name == "OPEN_STREET_MAP");

      if (firstChoice != null) {
        editStation[propName] = firstChoice.value;
      } else {
        editStation[propName] = '';
      }
    } else {
      editStation[propName] = '';
    }
  });

  unsourcedProperties.forEach((propName) => {
    if (data.station.properties[propName]) {
      editStation[propName] = data.station.properties[propName];
    } else {
      editStation[propName] = '';
    }
  });

  function addEmptyChargingPoint() {
    editStation.charging_points = [...editStation.charging_points, {}]
  }

  function removeChargingPoint(index: number) {
    editStation.charging_points = editStation.charging_points.toSpliced(index, 1);
  }

  let originalStation = structuredClone(editStation);
  let stationDiff = '';

  function promptChanges() {
    console.log(originalStation, editStation);

    stationDiff = '';

    for (const propName in originalStation) {
      if (originalStation[propName] != editStation[propName]) {
        stationDiff += propName + '-';
      }
    }
  }

  function managedChargingPoint(chargingPoint) {
    if (!chargingPoint.charging_groups || chargingPoint.charging_groups.length === 0) {
      return false;
    }

    if (chargingPoint.charging_groups.some((group) => group.network_id != null)) {
      return true;
    }

    return false;
  }

  function portLayoutForChargingPoint(chargingPoint) {
    let ports = [];

    if (!chargingPoint.charging_groups) {
      return "";
    }

    chargingPoint.charging_groups.forEach((group) => {
      if (!group.ports) {
        return;
      }

      group.ports.forEach((port) => {
        if (!port.plug_type) {
          return;
        }

        ports.push(port.plug_type);
      });
    });

    ports.sort();

    return ports.join(";");
  }

  function setPortLayoutForChargingPoint(index, portLayout) {
    let chargingGroups = [];
    let ports = portLayout.split(";");

    ports.forEach((port) => {
      chargingGroups.push({
        ports: [
          {
            plug_type: port
          }
        ]
      });
    });

    let chargingPoint = editStation.charging_points[index];

    chargingPoint.charging_groups = chargingGroups;

    editStation.charging_points[index] = chargingPoint;
  }

  function iconPathForPlugType(plugType: string): string {
    const PLUG_TYPE_MAP = {
      'CHADEMO': 'chademo',
      'J1772': 'j1772',
      'J1772_CABLE': 'j1772',
      'J1772_COMBO': 'j1772-combo',
      'NACS': 'nacs',
    }

    return base + '/icons/plug-' + PLUG_TYPE_MAP[plugType] + '.svg';
  }
</script>

<style>
  label {
    display: block;
  }

  input, select {
    border: 1px solid gray;
    display: block;
    width: 100%;
  }
</style>

<form on:submit|preventDefault={() => promptChanges()}>
  <label for="edit-station-name">Name</label>
  <input type="text" bind:value={editStation.name} list="edit-list-station-names" id="edit-station-name" />

  <datalist id="edit-list-station-names">
    {#each data.station.properties.name as nameChoice}
    <option value={nameChoice.value}>{nameChoice.value} ({nameChoice.source.name})</option>
    {/each}
  </datalist>

  <label for="edit-station-network">Network</label>
  <select bind:value={editStation.network} id="edit-station-network">
    <option value="">Unknown</option>
    <option value="NON_NETWORKED">Non-networked</option>
    <option value="AUTEL">Autel</option>
    <option value="CHARGEPOINT">ChargePoint</option>
    <option value="EVGO">EVgo</option>
    <option value="FLO">Flo</option>
    <option value="TESLA_DESTINATION">Tesla Destination</option>
    <option value="TESLA_SUPERCHARGER">Tesla Supercharger</option>
  </select>

  {#if editStation.network && editStation.network != "NON_NETWORKED"}
  <label for="edit-station-network-id">Network ID</label>
  <input type="text" bind:value={editStation.network_id} list="edit-list-station-network-ids" id="edit-station-network-id" />

  <datalist id="edit-list-station-network-ids">
    {#each data.station.properties.network_id as networkIdChoice}
    <option value={networkIdChoice.value}>{networkIdChoice.value} ({networkIdChoice.source.name})</option>
    {/each}
  </datalist>
  {/if}

  <h3>Charging Points</h3>
  {#each editStation.charging_points as chargingPoint, idx}
  <fieldset disabled={managedChargingPoint(chargingPoint)}>
    <label for={'edit-station-charging-points-' + idx + '-name'}>Name</label>
    <input type="text" bind:value={chargingPoint.name} id={'edit-station-charging-points-' + idx + '-name'} />

    <label for={'edit-station-charging-points-' + idx + '-ports'}>Ports</label>
    <select id={'edit-station-charging-points-' + idx + '-ports'} value={portLayoutForChargingPoint(chargingPoint)} on:change={(e) => setPortLayoutForChargingPoint(idx, e.target.value)}>
      <option value="">Unknown</option>
      <option value="J1772">J-1772</option>
      <option value="J1772_CABLE">J-1772 (with cable)</option>
      <option value="J1772_SOCKET">J-1772 (socket only)</option>
      <option value="J1772_CABLE;J1772_CABLE">Dual J-1772 (with cable)</option>
      <option value="J1772_COMBO">CCS 1</option>
      <option value="CHADEMO">CHADEMO</option>
      <option value="CHADEMO;J1772_COMBO">CCS 1 & CHADEMO</option>
    </select>
    {#if chargingPoint.charging_groups}
    {#each chargingPoint.charging_groups as chargingGroup}
    {#if chargingGroup.ports}
    {#each chargingGroup.ports as chargingPort}
    <img src={iconPathForPlugType(chargingPort.plug_type)} alt={chargingPort.plug_type} height="50px" width="50px" class="inline" />
    {/each}
    {/if}
    {/each}
    {/if}

    <button type="button" on:click={() => removeChargingPoint(idx)}>
      Delete charging point
    </button>
  </fieldset>
  {/each}
  <button type="button" on:click={addEmptyChargingPoint}>
    Add charging point
  </button>

  <button type="submit">
    Save
  </button>
</form>

{#if stationDiff}
{stationDiff}
{/if}

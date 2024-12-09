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
    address: {
      street_address: '',
      city: '',
      state: '',
      zip_code: '',
    },
    charging_points: [],
  };

  let sourcedProperties = ["name", "network_id"];
  let unsourcedProperties = ["charging_points", "network"];

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
  let stationDiff = "";

  function promptChanges() {
    console.log(originalStation, editStation);
    console.log(data.station.properties.references);

    let newTags = {};

    if (editStation.name) {
      newTags["name"] = editStation.name;
    }

    switch (editStation.network) {
      case "CHARGEPOINT":
        newTags["network"] = "ChargePoint";
        newTags["network:wikidata"] = "Q5176149";

        newTags["operator"] = "ChargePoint"
        newTags["operator:wikidata"] = "Q5176149";

        newTags["brand"] = "ChargePoint";
        newTags["brand:wikidata"] = "Q5176149";

        break;

      case "EVGO":
        newTags["network"] = "EVgo";
        newTags["network:wikidata"] = "Q61803820";

        newTags["operator"] = "EVgo"
        newTags["operator:wikidata"] = "Q61803820";

        newTags["brand"] = "EVgo";
        newTags["brand:wikidata"] = "Q61803820";

        break;

      case "TESLA_SUPERCHARGER":
        newTags["network"] = "Tesla Supercharger";
        newTags["network:wikidata"] = "Q17089620";

        newTags["operator"] = "Tesla, Inc."
        newTags["operator:wikidata"] = "Q478214";

        newTags["brand"] = "Tesla Supercharger";
        newTags["brand:wikidata"] = "Q17089620";

        break;
    }

    if (editStation.network_id) {
      newTags["ref:ocpi"] = editStation.network_id;
    }

    if (editStation.address.street_address) {
      let streetParts = editStation.address.street_address.split(" ");
      newTags["addr:housenumber"] = streetParts.unshift();
      newTags["addr:street"] = streetParts.join(" ");
    }

    if (editStation.address.city) {
      newTags["addr:city"] = editStation.address.city;
    }

    if (editStation.address.state) {
      newTags["addr:state"] = editStation.address.state;
    }

    if (editStation.address.zip_code) {
      newTags["addr:postcode"] = editStation.address.zip_code;
    }

    const PLUG_TO_SOCKET = {
      "CHADEMO": "chademo",
      "J1772": "type1_cable",
      "J1772_SOCKET": "type1",
      "J1772_COMBO": "type1_combo",
      "NACS": "tesla_supercharger",
    }

    let socketCounts = {
      "chademo": 0,
      "type1": 0,
      "type1_cable": 0,
      "type1_combo": 0,
      "tesla_supercharger": 0,
      "tesla_destination": 0,
    };

    for (const chargingPoint of editStation.charging_points) {
      for (const chargingGroup of chargingPoint.charging_groups) {
        for (const port of chargingGroup.ports) {
          socketCounts[PLUG_TO_SOCKET[port.plug_type]]++;
        }
      }
    }

    if (editStation.network == "TESLA_DESTINATION") {
      socketCounts["tesla_destination"] = socketCounts["tesla_supercharger"];
      socketCounts["tesla_supercharger"] = 0;
    }

    for (const socketName in socketCounts) {
      if (socketCounts[socketName] > 0) {
        newTags[`socket:${socketName}`] = socketCounts[socketName];
      }
    }

    if (data.station.properties.references) {
      let nrelIds = new Set();
      let ocmIds = new Set();

      for (let reference of data.station.properties.references) {
        if (reference.name == "ALTERNATIVE_FUELS_DATA_CENTER") {
          nrelIds.add(reference.url.split("/")[5]);
        }

        if (reference.name == "OPEN_CHARGE_MAP") {
          ocmIds.add(reference.url.split("/")[6]);
        }
      }

      if (nrelIds.size > 0) {
        newTags["ref:afdc"] = Array.from(nrelIds).join(";");
      }

      if (ocmIds.size > 0) {
        newTags["ref:ocm"] = Array.from(ocmIds).join(";");
      }
    }

    stationDiff = "";

    let tagNames = [... Object.keys(newTags)];
    tagNames.sort()

    for (const tagName of tagNames) {
      stationDiff += `${tagName}=${newTags[tagName]}\n`;
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

  textarea {
    border: 1px solid gray;
    display: block;
    height: 100px;
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

  <h3>Address</h3>
  <label for="edit-station-address-street-address">Street Address</label>
  <input type="text" bind:value={editStation.address.street_address} list="edit-list-station-address-street-address" id="edit-station-address-street-address" />

  <datalist id="edit-list-station-address-street-address">
    {#each data.station.properties.address as addressObject}
    {#if addressObject.address.street_address}
    <option value={addressObject.address.street_address}>{addressObject.address.street_address} ({addressObject.source.name})</option>
    {/if}
    {/each}
  </datalist>

  <label for="edit-station-address-city">City</label>
  <input type="text" bind:value={editStation.address.city} list="edit-list-station-address-city" id="edit-station-address-city" />

  <datalist id="edit-list-station-address-city">
    {#each data.station.properties.address as addressObject}
    {#if addressObject.address.city}
    <option value={addressObject.address.city}>{addressObject.address.city} ({addressObject.source.name})</option>
    {/if}
    {/each}
  </datalist>

  <label for="edit-station-address-state">State</label>
  <input type="text" bind:value={editStation.address.state} list="edit-list-station-address-state" id="edit-station-address-state" />

  <datalist id="edit-list-station-address-state">
    {#each data.station.properties.address as addressObject}
    {#if addressObject.address.state}
    <option value={addressObject.address.state}>{addressObject.address.state} ({addressObject.source.name})</option>
    {/if}
    {/each}
  </datalist>

  <label for="edit-station-address-zip-code">ZIP Code</label>
  <input type="text" bind:value={editStation.address.zip_code} list="edit-list-station-address-zip-code" id="edit-station-address-zip-code" />

  <datalist id="edit-list-station-address-zip-code">
    {#each data.station.properties.address as addressObject}
    {#if addressObject.address.zip_code}
    <option value={addressObject.address.zip_code}>{addressObject.address.zip_code} ({addressObject.source.name})</option>
    {/if}
    {/each}
  </datalist>

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
      <option value="NACS">NACS (Tesla)</option>
      <option value="CHADEMO;J1772_COMBO">CCS 1 & CHADEMO</option>
      <option value="J1772_COMBO;NACS">CCS 1 & NACS</option>
      <option value="CHADEMO;J1772_COMBO;NACS">CCS 1, NACS, CHADEMO</option>
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
<textarea>{stationDiff}</textarea>
{/if}

<script lang="ts">
import { page } from '$app/stores';
import { base } from "$app/paths";

import { firstPropertyValueForDisplay, formatSourceName, formatStationAddress } from "$lib/formatters";

function iconPathForPlugType(plugType: string): string {
  const PLUG_TYPE_MAP = {
    'CHADEMO': 'chademo',
    'J1772': 'j1772',
    'J1772_COMBO': 'j1772-combo',
    'NACS': 'nacs',
  }

  return base + '/icons/plug-' + PLUG_TYPE_MAP[plugType] + '.svg';
}

function* chunks<T>(arr: T[], n: number): Generator<T[], void> {
  for (let i = 0; i < arr.length; i += n) {
    yield arr.slice(i, i + n);
  }
}

export let data;
</script>
<a href="/networks/{$page.params.network}/stations/{$page.params.station}/edit">Edit</a>

{#if data.station.properties.name?.length > 1}
<h4 class="font-bold">
    Names
</h4>
<ul class="list-disc px-4">
    {#each data.station.properties.name as name}
    <li>
    {name.value}<br />
    <span class="italic">from <a href={name.source.url} class="underline" target="_blank">{formatSourceName(name.source.name)}</a></span>
    </li>
    {/each}
</ul>
{/if}
{#if data.station.properties.address?.length > 1}
<h4 class="font-bold">
    Addresses
</h4>
<ul class="list-disc px-4">
    {#each data.station.properties.address as address}
    <li>
    {formatStationAddress(address.address)}<br />
    <span class="italic">from <a href={address.source.url} class="underline" target="_blank">{formatSourceName(address.source.name)}</a></span>
    </li>
    {/each}
</ul>
{/if}
{#if data.station.properties.charging_points?.length > 0}
<h4 class="font-bold">
    Charging Points
</h4>
<div class="grid-cols-1 grid-cols-2 grid-cols-3"></div>
<div class="grid grid-cols-{Math.min(data.station.properties.charging_points.length, 3)} gap-4">
    {#each data.station.properties.charging_points as chargingPoint}
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
{#if data.station.properties.references?.length > 0}
<h4 class="font-bold">
    Sources
</h4>
<ul class="list-disc px-4">
    {#each data.station.properties.references as reference}
    <li>
    <a href={reference.url} class="underline" target="_blank">{formatSourceName(reference.name)}</a>
    </li>
    {/each}
    </ul>
{/if}
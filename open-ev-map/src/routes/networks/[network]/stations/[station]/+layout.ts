import { fetchStations } from "$lib/stations";
import type { PageLoad } from './$types';

async function fetchStationsForNetwork(network: string) {
  let allStations = await fetchStations();

  return allStations.filter((station) => station.properties.network == network.toUpperCase());
}

async function fetchStationForNetwork(network: string, networkId: string) {
  let stations = await fetchStationsForNetwork(network);

  return stations.find((station) => station.properties.network_id && station.properties.network_id.some((data) => data.value == networkId))
}

export const load: PageLoad = async ({ params }) => {
  let station = await fetchStationForNetwork(params.network, params.station);

  return {
    params: params,
    station: station,
  };
};
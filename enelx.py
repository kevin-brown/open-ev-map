import json
import pathlib

enel_files = pathlib.Path("./scraped_data/enelx_stations/")

for file in enel_files.glob("*.json"):
    if not file.is_file():
        continue

    with file.open() as fh:
        data = json.load(fh)

    tenant_id = data["tenantId"]
    evse = data["evses"][0]
    evse_id = evse["evseId"]
    cpo_id = evse_id[3:6]

    if tariff := evse["plugs"][0]["tariffPlan"]:
        tenant_owner_id = tariff["tenantOwnerId"]
        tenant_owner_role = tariff["tenantOwnerRole"]
    else:
        tenant_owner_id = ""
        tenant_owner_role = "   "

    print(f"{tenant_id:<40} {cpo_id} {tenant_owner_role} {tenant_owner_id}")

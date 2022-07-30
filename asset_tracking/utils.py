import os
import json
import logging

from sqlalchemy.orm import Session

from asset_tracking.database.operations import (
    get_all_assets,
    get_asset_attributes,
    delete_asset,
)


def load_asset_data_from_json_file(file_path: str):
    if not os.path.exists:
        logging.error(f"{file_path} not found.")
        return False
    data = None
    with open(file_path, "r") as fp:
        data = json.load(fp)

    return data


def export_database_to_json_report(session: Session):
    # Make columns like: name, status, last_seen, attribute, attribute
    # and then set last_seen for the attribute or None if none.
    import datetime

    data = []
    for asset in get_all_assets(session):
        if asset.hostname.endswith("$"):
            delete_asset(session, asset)
            continue
        asset_data = asset.to_dict()
        for attribute in get_asset_attributes(session, asset):
            asset_data[attribute.name] = (
                attribute.last_observed.strftime("%Y-%m-%d %H:%M:%S")
                if attribute.last_observed
                else attribute.last_observed
            )
        data.append(asset_data)

    now = datetime.datetime.now().replace(microsecond=0).isoformat()
    with open(f"asset_tracking_{now}.json", "w") as f:
        f.write(json.dumps(data, default=str))

    return True
